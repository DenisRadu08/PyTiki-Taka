import os
import glob
import json
import time
import datetime
import random
import argparse
import multiprocessing
from ai_brains import DEFAULT_GENOME, GENOME_BOUNDS
from headless_sim import simulate_match


def genome_signature(genome):
    return tuple(genome[k] for k in sorted(DEFAULT_GENOME.keys()))


def clamp_gene(key, val):
    lo, hi = GENOME_BOUNDS[key]
    decimals = 2 if key in ("def_mark_weight", "attack_support_push") else 1
    return round(max(lo, min(hi, float(val))), decimals)


def sanitize_genome(raw_g):
    merged = dict(DEFAULT_GENOME)
    if isinstance(raw_g, dict):
        for k, v in raw_g.items():
            if k in merged:
                merged[k] = clamp_gene(k, v)
    return merged


def random_mutated_genome(base_genome, sigma_scale=0.18, mutation_prob=0.55):
    g = dict(base_genome)
    for k, (lo, hi) in GENOME_BOUNDS.items():
        if random.random() < mutation_prob:
            span = hi - lo
            g[k] = clamp_gene(k, g[k] + random.gauss(0.0, span * sigma_scale))
    return g


def crossover_genomes(parent1, parent2):
    """
    Blend Crossover (BLX-alpha) + Uniform Gene Mix.
    """
    child = {}
    for k in DEFAULT_GENOME.keys():
        if random.random() < 0.5:
            alpha = random.uniform(-0.15, 1.15)
            val = parent1[k] * alpha + parent2[k] * (1.0 - alpha)
            child[k] = clamp_gene(k, val)
        else:
            child[k] = parent1[k] if random.random() < 0.5 else parent2[k]
    return child


def compute_match_fitness(gf, ga, xgf, xga, poss, acc):
    return (
        4.0 * (gf - ga)
        + 2.5 * (xgf - xga)
        + 0.04 * (poss - 50.0)
        + 0.02 * (acc - 70.0)
    )


def evaluate_vs_opponents_worker(args):
    """
    Evalueaza un genom pe o lista de adversari (tur-retur: 50% ca Echipa A, 50% ca Echipa B).
    Foloseste Common Random Numbers (CRN): toti candidatii din aceeasi generatie joaca pe
    aceleasi seed-uri pereche (base_seed + m * 37), reducand drastic factorul de noroc!
    """
    idx, genome, opponents_list, max_ticks, base_seed = args
    tot_fit = 0.0
    wins = draws = losses = 0
    tot_gf = tot_ga = 0
    tot_xgf = tot_xga = 0.0
    tot_poss = tot_acc = 0.0
    n = len(opponents_list)

    for m, opp_genome in enumerate(opponents_list):
        play_as_a = (m % 2 == 0)
        # Common Random Numbers (CRN): aceleasi conditii aleatorii pentru toti candidatii generatiei
        m_seed = base_seed + m * 37

        if play_as_a:
            res = simulate_match(genome_a=genome, genome_b=opp_genome, max_ticks=max_ticks, seed=m_seed)
            gf, ga = res["score_A"], res["score_B"]
            xgf, xga = res["xg_A"], res["xg_B"]
            poss, acc = res["poss_A"], res["pass_acc_A"]
        else:
            res = simulate_match(genome_a=opp_genome, genome_b=genome, max_ticks=max_ticks, seed=m_seed)
            gf, ga = res["score_B"], res["score_A"]
            xgf, xga = res["xg_B"], res["xg_A"]
            poss, acc = res["poss_B"], res["pass_acc_B"]

        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1

        tot_fit += compute_match_fitness(gf, ga, xgf, xga, poss, acc)
        tot_gf += gf
        tot_ga += ga
        tot_xgf += xgf
        tot_xga += xga
        tot_poss += poss
        tot_acc += acc

    nf = float(max(1, n))
    return {
        "idx": idx,
        "matches": n,
        "fitness": tot_fit / nf,
        "points": wins * 3 + draws,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "win_rate": round((wins / nf) * 100.0, 1),
        "avg_gf": round(tot_gf / nf, 2),
        "avg_ga": round(tot_ga / nf, 2),
        "avg_xgf": round(tot_xgf / nf, 2),
        "avg_xga": round(tot_xga / nf, 2),
        "avg_poss": round(tot_poss / nf, 1),
        "avg_acc": round(tot_acc / nf, 1),
    }


SIM_VERSION = "true_engine_v1"


def save_model_file(best_genome, best_metrics, stage_info, total_matches, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    payload = {
        "build_name": "Genetic AI (GA)",
        "sim_version": SIM_VERSION,
        "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage_info": stage_info,
        "total_matches_simulated": total_matches,
        "metrics": best_metrics,
        "genome": best_genome,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=4)


def load_all_archived_champions():
    """
    Incarca models/genetic_best.json si toti campionii din models/genetic_archive/*.json.
    ATENTIE: Recordul global (best_global_fit) este luat in considerare DOAR din modelele
    validate pe motorul real 1:1 (sim_version == "true_engine_v1"), astfel incat scorurile
    umflate din vechiul simulator simplificat sa nu blocheze salvarea campionilor reali!
    """
    champs = []
    true_champs = []
    seen = set()
    best_global_fit = -9999.0
    legacy_best_detected = False

    paths = ["models/genetic_best.json"] + sorted(glob.glob("models/genetic_archive/*.json"))
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r") as f:
                data = json.load(f)
                g = sanitize_genome(data.get("genome", {}))
                fit = float(data.get("metrics", {}).get("fitness", -9999.0))
                ver = data.get("sim_version", "legacy_simplified")
                if p == "models/genetic_best.json":
                    if ver == SIM_VERSION:
                        best_global_fit = fit
                    else:
                        legacy_best_detected = True
                sig = genome_signature(g)
                if sig not in seen:
                    seen.add(sig)
                    if ver == SIM_VERSION:
                        true_champs.append((fit, g, os.path.basename(p)))
                    else:
                        champs.append((fit, g, os.path.basename(p)))
        except Exception:
            pass

    true_champs.sort(key=lambda x: x[0], reverse=True)
    champs.sort(key=lambda x: x[0], reverse=True)
    return true_champs, champs, best_global_fit, legacy_best_detected


def run_league_evolution(stage1_gens=70, stage3_gens=60, pop_size=36, matches_per_ind=12, max_ticks=1800, hof_size=30, final_matches=100, workers=None):
    os.makedirs("models", exist_ok=True)
    os.makedirs("models/genetic_archive", exist_ok=True)
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)

    run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_archive_path = f"models/genetic_archive/genetic_league_{run_ts}.json"
    checkpoint_path = "models/genetic_archive/checkpoint_latest.json"
    true_champs, legacy_champs, global_best_fit, legacy_best_detected = load_all_archived_champions()

    print("=" * 88)
    print("  PyTiki-Taka — HALL-OF-FAME LEAGUE CO-EVOLUTION (TRUE-ENGINE 1:1 + ANTI-LUCK CRN)")
    print(f"  Etapa 1 (vs Base Build): {stage1_gens} gen ({matches_per_ind}m/echipa) | Etapa 2: Liga Top {hof_size} (30m)")
    print(f"  Etapa 3 (Boss Co-Evo):   {stage3_gens} gen (14m/echipa) | Etapa 4: Examen Final {final_matches}m vs Base + H2H")
    print(f"  Populatie: {pop_size} | Ticks: {max_ticks} ({max_ticks*0.05:.0f}s / 2 reprize) | Nuclee CPU: {workers} | CRN: ACTIV")
    if legacy_best_detected:
        print(f"  NOTA: models/genetic_best.json anterior era din simulatorul simplificat -> recordul global real porneste curat!")
    else:
        print(f"  Campion global curent (True-Engine 1:1): Fitness {global_best_fit:+.2f} | Campioni 1:1 arhiva: {len(true_champs)}")
    print(f"  Arhiva finala: {run_archive_path} | Checkpoint auto: fiecare 10 gen")
    print("=" * 88)

    total_matches_done = 0
    history = []
    start_time = time.time()

    # =========================================================================
    # ETAPA 1: EVOLUTIE CURATA 100% CONTRA BASE BUILD + HALL OF FAME CUMULATIV
    # =========================================================================
    print("\n>>> [ETAPA 1/4] EVOLUTIE PURA CONTRA BASE BUILD (comparatie 100% corecta intre generatii)...")
    seen_offspring = set()
    population = [dict(DEFAULT_GENOME)]
    seen_offspring.add(genome_signature(population[0]))

    # Adaugam campionii validati pe True-Engine 1:1 direct in Generatia 0!
    for _, cg, cname in true_champs[:min(6, pop_size // 3)]:
        sig_c = genome_signature(cg)
        if sig_c not in seen_offspring:
            seen_offspring.add(sig_c)
            population.append(dict(cg))

    # Pornim mutatiile din campionii True-Engine 1:1 (daca exista) + Base Build curat (fara bias din vechiul sim!)
    seed_parents = [g for _, g, _ in true_champs[:4]] + [dict(DEFAULT_GENOME)]
    while len(population) < pop_size:
        # 20% explorare complet aleatorie in spatiul celor 26 de gene, 80% mutatii in jurul parintilor curati
        if random.random() < 0.20:
            cand = {k: clamp_gene(k, random.uniform(lo, hi)) for k, (lo, hi) in GENOME_BOUNDS.items()}
        else:
            parent = random.choice(seed_parents)
            cand = random_mutated_genome(parent, sigma_scale=0.22, mutation_prob=0.65)
        sig = genome_signature(cand)
        if sig not in seen_offspring:
            seen_offspring.add(sig)
            population.append(cand)

    # Hall of Fame cumulativ: {sig: {"genome": g, "sum_fit": float, "evals": int, "best_res": dict}}
    hof_registry = {}

    def register_in_hof(genome, res):
        sig = genome_signature(genome)
        if sig not in hof_registry:
            hof_registry[sig] = {"genome": dict(genome), "sum_fit": res["fitness"], "evals": 1, "last_res": res}
        else:
            hof_registry[sig]["sum_fit"] += res["fitness"]
            hof_registry[sig]["evals"] += 1
            hof_registry[sig]["last_res"] = res

    try:
        with multiprocessing.Pool(processes=workers) as pool:
            base_opps = [DEFAULT_GENOME] * matches_per_ind

            for gen in range(1, stage1_gens + 1):
                gen_t0 = time.time()
                gen_seed = int(time.time() * 100) % 100000 + gen * 10007
                tasks = [(i, population[i], base_opps, max_ticks, gen_seed) for i in range(pop_size)]
                results = pool.map(evaluate_vs_opponents_worker, tasks)
                total_matches_done += pop_size * matches_per_ind

                for r, g in zip(results, population):
                    register_in_hof(g, r)

                paired = sorted(zip(results, population), key=lambda x: x[0]["fitness"], reverse=True)
                best_res, best_g = paired[0]
                avg_fit = sum(r["fitness"] for r, _ in paired) / pop_size
                gen_dt = time.time() - gen_t0
                elapsed = time.time() - start_time

                print(
                    f"[S1 Gen {gen:03d}/{stage1_gens:03d}] "
                    f"BestFit: {best_res['fitness']:+6.2f} (Avg: {avg_fit:+5.2f}) | "
                    f"WR: {best_res['win_rate']:5.1f}% | "
                    f"Gol: {best_res['avg_gf']:.2f}-{best_res['avg_ga']:.2f} | "
                    f"xG: {best_res['avg_xgf']:.2f}-{best_res['avg_xga']:.2f} | "
                    f"Poss: {best_res['avg_poss']:4.1f}% | "
                    f"Unice: {len(seen_offspring)} | {gen_dt:.1f}s"
                )

                history.append({
                    "stage": 1, "generation": gen,
                    "best_fitness": round(best_res["fitness"], 3), "avg_fitness": round(avg_fit, 3),
                    "best_wr": best_res["win_rate"], "best_gf": best_res["avg_gf"], "best_ga": best_res["avg_ga"],
                    "best_xgf": best_res["avg_xgf"], "best_xga": best_res["avg_xga"], "best_poss": best_res["avg_poss"],
                    "unique_tested": len(seen_offspring), "elapsed_sec": round(elapsed, 1),
                })

                # Checkpoint automat la fiecare 10 generatii (protectie anti-crash pentru rulari de 6-7 ore!)
                if gen % 10 == 0:
                    top_cp = sorted(
                        hof_registry.values(),
                        key=lambda item: (item["sum_fit"] / item["evals"]) + min(1.5, item["evals"] * 0.15),
                        reverse=True
                    )[0]
                    save_model_file(top_cp["genome"], top_cp["last_res"], {"checkpoint": f"Stage1_Gen{gen}"}, total_matches_done, out_path=checkpoint_path)
                    with open("models/genetic_history.json", "w") as hf:
                        json.dump(history, hf, indent=2)
                    print(f"    [Checkpoint] Salvat progresul la S1 Gen {gen} ({total_matches_done} meciuri, {elapsed/60.0:.1f} min)")

                # Generatia urmatoare: 15% Elitism (re-evaluate!), 10% Imigranti noi, 75% Crossover+Mutatie deduplicate
                elite_n = max(3, int(pop_size * 0.15))
                imm_n = max(2, int(pop_size * 0.10))
                next_pop = [dict(g) for _, g in paired[:elite_n]]

                for _ in range(imm_n):
                    imm = {k: clamp_gene(k, random.uniform(lo, hi)) for k, (lo, hi) in GENOME_BOUNDS.items()}
                    sig_i = genome_signature(imm)
                    if sig_i not in seen_offspring:
                        seen_offspring.add(sig_i)
                        next_pop.append(imm)

                prog = gen / float(max(1, stage1_gens))
                sigma = 0.20 * (1.0 - 0.65 * prog) + 0.04
                mut_p = 0.48 * (1.0 - 0.45 * prog) + 0.16
                top_pool = [g for _, g in paired[:max(6, pop_size // 2)]]
                attempts = 0
                while len(next_pop) < pop_size:
                    attempts += 1
                    child = crossover_genomes(random.choice(top_pool), random.choice(top_pool))
                    child = random_mutated_genome(child, sigma_scale=sigma, mutation_prob=mut_p)
                    sig_c = genome_signature(child)
                    if sig_c not in seen_offspring or attempts > 60:
                        seen_offspring.add(sig_c)
                        next_pop.append(child)
                        attempts = 0
                population = next_pop

            # Selectam Top 'hof_size' candidati din Hall of Fame (dupa media cumulativa de Fitness!)
            hof_ranked = sorted(
                hof_registry.values(),
                key=lambda item: (item["sum_fit"] / item["evals"]) + min(1.5, item["evals"] * 0.15),
                reverse=True
            )
            hof_candidates = [item["genome"] for item in hof_ranked[:hof_size]]
            stage1_champ = hof_candidates[0]
            stage1_runnerup = hof_candidates[1] if len(hof_candidates) > 1 else hof_candidates[0]

            # =====================================================================
            # ETAPA 2: LIGA CAMPIONILOR (TOP 30 HALL OF FAME JOACA 30 MECIURI FIECARE!)
            # =====================================================================
            print(f"\n>>> [ETAPA 2/4] LIGA CAMPIONILOR: Top {len(hof_candidates)} echipe din Hall of Fame joaca cate 30 meciuri (20 H2H + 10 Base)!")
            t_s2 = time.time()
            league_tasks = []
            rng_l = random.Random(4242)
            for idx_h, g_h in enumerate(hof_candidates):
                # Fiecare echipa joaca contra a 10 rivali diferiti din Top 30 (tur-retur = 20 meciuri) + 10 meciuri vs Base Build = 30 meciuri!
                others = [g for j, g in enumerate(hof_candidates) if j != idx_h]
                rivals = rng_l.sample(others, min(10, len(others)))
                opps = []
                for rv in rivals:
                    opps.append(rv)
                    opps.append(rv)
                opps.extend([DEFAULT_GENOME] * 10)
                league_tasks.append((idx_h, g_h, opps, max_ticks, 200000))

            league_results = pool.map(evaluate_vs_opponents_worker, league_tasks)
            total_matches_done += sum(len(t[2]) for t in league_tasks)

            league_table = sorted(
                zip(league_results, hof_candidates),
                key=lambda x: (x[0]["points"], x[0]["fitness"]),
                reverse=True
            )
            boss_league = [g for _, g in league_table[:4]]
            print(f"    Liga incheiata in {time.time() - t_s2:.1f}s! Clasament TOP 4 (Boss League):")
            for rank, (lr, _) in enumerate(league_table[:4], 1):
                print(
                    f"    #{rank}: Puncte={lr['points']:2d} | WR={lr['win_rate']:5.1f}% | "
                    f"Fit={lr['fitness']:+6.2f} | Gol={lr['avg_gf']:.2f}-{lr['avg_ga']:.2f} | xG={lr['avg_xgf']:.2f}-{lr['avg_xga']:.2f}"
                )

            # =====================================================================
            # ETAPA 3: CO-EVOLUTIE "BOSS MODE" CONTRA TOP 4 CAMPIONI AI LIGII!
            # =====================================================================
            print(f"\n>>> [ETAPA 3/4] CO-EVOLUTIE 'BOSS MODE': {stage3_gens} generatii care se lupta contra Top 4 Campioni!")
            # Populam Etapa 3 pornind de la Top 4 Boss League + mutatii/crossover intre ei
            s3_pop = [dict(g) for g in boss_league]
            s3_seen = set(genome_signature(g) for g in s3_pop)
            while len(s3_pop) < pop_size:
                if random.random() < 0.65:
                    child = crossover_genomes(random.choice(boss_league), random.choice(boss_league))
                    child = random_mutated_genome(child, sigma_scale=0.14, mutation_prob=0.55)
                else:
                    child = random_mutated_genome(random.choice(hof_candidates[:10]), sigma_scale=0.18, mutation_prob=0.60)
                sig_s3 = genome_signature(child)
                if sig_s3 not in s3_seen:
                    s3_seen.add(sig_s3)
                    s3_pop.append(child)

            # Lista fixa de adversari pentru Etapa 3: 2 meciuri vs FIECARE dintre cei 4 Boss Champions (8) + 6 vs Base Build = 14 meciuri!
            boss_opps = []
            for bg in boss_league:
                boss_opps.append(bg)
                boss_opps.append(bg)
            boss_opps.extend([DEFAULT_GENOME] * 6)

            s3_hof = {}
            for gen3 in range(1, stage3_gens + 1):
                gen_t0 = time.time()
                gen_seed = int(time.time() * 100) % 100000 + 500000 + gen3 * 10009
                tasks3 = [(i, s3_pop[i], boss_opps, max_ticks, gen_seed) for i in range(pop_size)]
                res3 = pool.map(evaluate_vs_opponents_worker, tasks3)
                total_matches_done += pop_size * len(boss_opps)

                for r, g in zip(res3, s3_pop):
                    sig = genome_signature(g)
                    if sig not in s3_hof:
                        s3_hof[sig] = {"genome": dict(g), "sum_fit": r["fitness"], "evals": 1}
                    else:
                        s3_hof[sig]["sum_fit"] += r["fitness"]
                        s3_hof[sig]["evals"] += 1

                paired3 = sorted(zip(res3, s3_pop), key=lambda x: x[0]["fitness"], reverse=True)
                best_r3, _ = paired3[0]
                avg_f3 = sum(r["fitness"] for r, _ in paired3) / pop_size
                gen_dt = time.time() - gen_t0
                elapsed = time.time() - start_time

                print(
                    f"[S3 Gen {gen3:03d}/{stage3_gens:03d}] "
                    f"BossFit: {best_r3['fitness']:+6.2f} (Avg: {avg_f3:+5.2f}) | "
                    f"WR vs Boss: {best_r3['win_rate']:5.1f}% | "
                    f"Gol: {best_r3['avg_gf']:.2f}-{best_r3['avg_ga']:.2f} | "
                    f"xG: {best_r3['avg_xgf']:.2f}-{best_r3['avg_xga']:.2f} | {gen_dt:.1f}s"
                )

                history.append({
                    "stage": 3, "generation": gen3,
                    "best_fitness": round(best_r3["fitness"], 3), "avg_fitness": round(avg_f3, 3),
                    "best_wr": best_r3["win_rate"], "best_gf": best_r3["avg_gf"], "best_ga": best_r3["avg_ga"],
                    "best_xgf": best_r3["avg_xgf"], "best_xga": best_r3["avg_xga"], "best_poss": best_r3["avg_poss"],
                    "elapsed_sec": round(elapsed, 1),
                })

                if gen3 % 10 == 0:
                    top_cp3 = sorted(s3_hof.values(), key=lambda x: (x["sum_fit"] / x["evals"]) + min(1.5, x["evals"] * 0.15), reverse=True)[0]
                    save_model_file(top_cp3["genome"], best_r3, {"checkpoint": f"Stage3_Gen{gen3}"}, total_matches_done, out_path=checkpoint_path)
                    with open("models/genetic_history.json", "w") as hf:
                        json.dump(history, hf, indent=2)
                    print(f"    [Checkpoint] Salvat progresul la S3 Gen {gen3} ({total_matches_done} meciuri, {elapsed/60.0:.1f} min)")

                elite_n = max(3, int(pop_size * 0.15))
                imm_n = max(2, int(pop_size * 0.10))
                next_s3 = [dict(g) for _, g in paired3[:elite_n]]
                for _ in range(imm_n):
                    imm = random_mutated_genome(random.choice(boss_league), sigma_scale=0.22, mutation_prob=0.65)
                    s3_seen.add(genome_signature(imm))
                    next_s3.append(imm)

                prog3 = gen3 / float(max(1, stage3_gens))
                sigma3 = 0.15 * (1.0 - 0.65 * prog3) + 0.03
                mut_p3 = 0.42 * (1.0 - 0.45 * prog3) + 0.14
                top_pool3 = [g for _, g in paired3[:max(6, pop_size // 2)]]
                attempts = 0
                while len(next_s3) < pop_size:
                    attempts += 1
                    child = crossover_genomes(random.choice(top_pool3), random.choice(top_pool3))
                    child = random_mutated_genome(child, sigma_scale=sigma3, mutation_prob=mut_p3)
                    sig_c = genome_signature(child)
                    if sig_c not in s3_seen or attempts > 60:
                        s3_seen.add(sig_c)
                        next_s3.append(child)
                        attempts = 0
                s3_pop = next_s3

            # =====================================================================
            # ETAPA 4: EXAMENUL FINAL ANTI-NOROC (100 MECIURI VS BASE BUILD + MINI-LIGA FINALISTI)
            # =====================================================================
            s3_ranked = sorted(s3_hof.values(), key=lambda x: (x["sum_fit"] / x["evals"]) + min(1.5, x["evals"] * 0.15), reverse=True)
            raw_finalists = [
                ("Stage1_#1", stage1_champ),
                ("Stage1_#2", stage1_runnerup),
                ("League_#1", boss_league[0]),
                ("League_#2", boss_league[1] if len(boss_league) > 1 else boss_league[0]),
                ("BossCoEvo_#1", s3_ranked[0]["genome"]),
                ("BossCoEvo_#2", s3_ranked[1]["genome"] if len(s3_ranked) > 1 else s3_ranked[0]["genome"]),
            ]
            finalists = []
            seen_fin = set()
            for lbl, fg in raw_finalists:
                sf = genome_signature(fg)
                if sf not in seen_fin:
                    seen_fin.add(sf)
                    finalists.append((lbl, fg))

            print(f"\n>>> [ETAPA 4/4] EXAMENUL FINAL ANTI-NOROC: {len(finalists)} Finalisti joaca cate {final_matches} meciuri vs Base Build (CRN identic) + Mini-Liga directa (12m/pereche)!")
            val_tasks = [(i, fg, [DEFAULT_GENOME] * final_matches, max_ticks, 900000) for i, (_, fg) in enumerate(finalists)]
            val_results = pool.map(evaluate_vs_opponents_worker, val_tasks)
            total_matches_done += len(finalists) * final_matches

            # Mini-liga directa intre finalisti (cate 12 meciuri tur-retur cu fiecare alt finalist!)
            h2h_tasks = []
            for i, (_, fg) in enumerate(finalists):
                opps_f = []
                for j, (_, og) in enumerate(finalists):
                    if i != j:
                        opps_f.extend([og] * 12)
                h2h_tasks.append((i, fg, opps_f, max_ticks, 950000))
            h2h_results = pool.map(evaluate_vs_opponents_worker, h2h_tasks)
            total_matches_done += sum(len(t[2]) for t in h2h_tasks)

            final_board = []
            for (lbl, fg), vr, hr in zip(finalists, val_results, h2h_results):
                # Scor combinat: 65% performanta pe 100 meciuri vs Base Build + 35% dominanta directa contra celorlalti finalisti!
                combined = 0.65 * vr["fitness"] + 0.35 * hr["fitness"]
                final_board.append((combined, lbl, fg, vr, hr))
                print(
                    f"    {lbl:14s} | {final_matches}m vs Base: {vr['wins']:2d}W-{vr['draws']:2d}D-{vr['losses']:2d}L "
                    f"(WR {vr['win_rate']:5.1f}%, Fit {vr['fitness']:+6.2f}, Gol {vr['avg_gf']:.2f}-{vr['avg_ga']:.2f}, xG {vr['avg_xgf']:.2f}-{vr['avg_xga']:.2f}) "
                    f"| H2H Finala: WR {hr['win_rate']:5.1f}% (Fit {hr['fitness']:+5.2f})"
                )

            final_board.sort(key=lambda x: x[0], reverse=True)
            _, win_lbl, champ_genome, champ_val, champ_h2h = final_board[0]

            with open("models/genetic_history.json", "w") as hf:
                json.dump(history, hf, indent=2)

            stage_meta = {
                "winner_source": win_lbl,
                "stage1_gens": stage1_gens,
                "stage3_gens": stage3_gens,
                "final_validation_matches": final_matches,
                "h2h_win_rate": champ_h2h["win_rate"],
                "h2h_fitness": round(champ_h2h["fitness"], 3),
            }
            save_model_file(champ_genome, champ_val, stage_meta, total_matches_done, out_path=run_archive_path)

            print("\n" + "=" * 88)
            print(f"  CAMPIONUL SUPREM ({win_lbl}) - VALIDAT PE {final_matches} MECIURI REALE 1:1 VS BASE BUILD:")
            print(
                f"  Bilant: {champ_val['wins']}W - {champ_val['draws']}D - {champ_val['losses']}L "
                f"(Win Rate: {champ_val['win_rate']}% | Fitness: {champ_val['fitness']:+.2f})"
            )
            print(
                f"  Goluri: {champ_val['avg_gf']:.2f} - {champ_val['avg_ga']:.2f} | "
                f"xG: {champ_val['avg_xgf']:.2f} - {champ_val['avg_xga']:.2f} | "
                f"Posesie: {champ_val['avg_poss']:.1f}% | Pase: {champ_val['avg_acc']:.1f}%"
            )
            print(f"  Total meciuri simulate in acest run: {total_matches_done} | Arhiva: {run_archive_path}")

            if champ_val["fitness"] > global_best_fit:
                save_model_file(champ_genome, champ_val, stage_meta, total_matches_done, out_path="models/genetic_best.json")
                print(f"  NOU RECORD GLOBAL! models/genetic_best.json actualizat ({global_best_fit:+.2f} -> {champ_val['fitness']:+.2f})!")
            else:
                print(f"  Recordul anterior din models/genetic_best.json ramane activ ({global_best_fit:+.2f} >= {champ_val['fitness']:+.2f}).")
            print("=" * 84)

    except KeyboardInterrupt:
        print("\nAntrenare oprita manual (Ctrl+C). Salvam cel mai bun candidat gasit pana acum in arhiva...")
        if hof_registry:
            top_now = sorted(hof_registry.values(), key=lambda x: x["sum_fit"] / x["evals"], reverse=True)[0]
            save_model_file(top_now["genome"], top_now["last_res"], {"interrupted": True}, total_matches_done, out_path=run_archive_path)
            print(f"Salvat in {run_archive_path}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="PyTiki-Taka Hall-of-Fame League Co-Evolution Trainer")
    parser.add_argument("--stage1-gens", type=int, default=70, help="Generatii Etapa 1 vs Base Build (default: 70)")
    parser.add_argument("--stage3-gens", type=int, default=60, help="Generatii Etapa 3 Boss Co-Evolution (default: 60)")
    parser.add_argument("--pop", type=int, default=36, help="Marimea populatiei (default: 36)")
    parser.add_argument("--matches", type=int, default=12, help="Meciuri per individ in Etapa 1 (default: 12)")
    parser.add_argument("--ticks", type=int, default=1800, help="Ticks per meci 2 reprize (default: 1800 = 90s real)")
    parser.add_argument("--hof", type=int, default=30, help="Numar echipe in Hall of Fame League (default: 30)")
    parser.add_argument("--final-matches", type=int, default=100, help="Meciuri de validare finala vs Base Build (default: 100)")
    parser.add_argument("--workers", type=int, default=None, help="Nuclee CPU (default: auto)")
    args = parser.parse_args()

    run_league_evolution(
        stage1_gens=args.stage1_gens,
        stage3_gens=args.stage3_gens,
        pop_size=args.pop,
        matches_per_ind=args.matches,
        max_ticks=args.ticks,
        hof_size=args.hof,
        final_matches=args.final_matches,
        workers=args.workers,
    )
