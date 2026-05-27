#!/usr/bin/env python3
"""
bench_sparql.py — compare pyoxigraph vs rdflib SPARQL backends for owlready2.

Usage:  PYTHONPATH=/Users/remzicelebi/workspace/claude-ws python3 owlready2/test/bench_sparql.py
"""

import os, sys, time, statistics, gc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import owlready2
from owlready2 import *

HERE  = os.path.dirname(os.path.abspath(__file__))
ROOT  = os.path.dirname(HERE)                      # owlready2/
DIST  = os.path.join(ROOT, "..", "sulo-tutorial", "dist")
MIE05 = os.path.join(DIST, "mie-05.owl")

SIMPLE_TEST_OWL = "http://www.semanticweb.org/jiba/ontologies/2017/0/test"

QUERIES = [
    (
        "all individuals + types (SELECT *)",
        """SELECT ?s ?t WHERE {
             ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>
                <http://www.w3.org/2002/07/owl#NamedIndividual> .
             ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?t .
           }""",
    ),
    (
        "all classes (SELECT)",
        """SELECT ?c WHERE {
             ?c <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>
                <http://www.w3.org/2002/07/owl#Class> .
           }""",
    ),
    (
        "subClassOf chains",
        """SELECT ?child ?parent WHERE {
             ?child <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?parent .
           }""",
    ),
    (
        "restrictions (onProperty + someValuesFrom)",
        """SELECT ?cls ?prop ?val WHERE {
             ?cls <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?r .
             ?r   <http://www.w3.org/2002/07/owl#onProperty>        ?prop .
             ?r   <http://www.w3.org/2002/07/owl#someValuesFrom>     ?val .
           }""",
    ),
    (
        "data properties (label / comment)",
        """SELECT ?s ?label WHERE {
             ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label .
           }""",
    ),
    (
        "all triples (full dump)",
        "SELECT ?s ?p ?o WHERE { ?s ?p ?o . }",
    ),
]

WARMUP   = 2
REPEATS  = 10
COL_W    = 42

# ── store-build cost measurement ──────────────────────────────────────────────

def measure_store_build(world):
    from owlready2.pyoxigraph_store import _build_ox_store
    med, std, _ = timeit(lambda: _build_ox_store(world), WARMUP, REPEATS)
    return med


# ── rdflib backend ────────────────────────────────────────────────────────────

def make_rdflib_graph(world):
    from owlready2.rdflib_store import TripleLiteRDFlibStore, TripleLiteRDFlibGraph
    store = TripleLiteRDFlibStore(world)
    g = TripleLiteRDFlibGraph(store=store)
    g.triplelite = world.graph
    return g

def run_rdflib(g, sparql):
    return list(g.query_owlready(sparql))


# ── pyoxigraph backend ────────────────────────────────────────────────────────

def make_ox_graph(world):
    from owlready2.pyoxigraph_store import OxigraphGraph
    return OxigraphGraph(world)

def run_ox(g, sparql):
    return list(g.query_owlready(sparql))


# ── timing helper ─────────────────────────────────────────────────────────────

def timeit(fn, warmup, repeats):
    for _ in range(warmup):
        fn()
    gc.collect()
    times = []
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), statistics.stdev(times), result


def timeit_safe(fn, warmup, repeats):
    """Like timeit but returns (None, None, error_msg) on exception."""
    try:
        return timeit(fn, warmup, repeats)
    except Exception as e:
        return None, None, f"ERROR: {type(e).__name__}: {e}"


# ── benchmark runner ──────────────────────────────────────────────────────────

def benchmark(world, make_graph, run_fn):
    g = make_graph(world)
    results = {}
    for name, sparql in QUERIES:
        med, std, rows = timeit_safe(lambda s=sparql: run_fn(g, s), WARMUP, REPEATS)
        if med is None:
            results[name] = (None, None, rows)   # rows holds error string
        else:
            results[name] = (med, std, len(rows))
    return results


def print_table(results_rdflib, results_ox):
    header = f"{'Query':<{COL_W}}  {'rdflib (ms)':>12}  {'pyoxigraph (ms)':>15}  {'speedup':>8}  {'rows':>6}"
    print(header)
    print("-" * len(header))
    speedups = []
    for name, _ in QUERIES:
        rl_med, rl_std, rl_rows = results_rdflib[name]
        ox_med, ox_std, ox_rows = results_ox[name]
        short = (name[:COL_W-1] + "…") if len(name) > COL_W else name

        if rl_med is None:
            rl_cell = f"{'CRASH':>12}"
            speedup_cell = f"{'N/A':>8}"
        else:
            rl_cell = f"{rl_med*1000:>10.2f}ms"
            speedup = rl_med / ox_med
            speedups.append(speedup)
            arrow = "▲" if speedup >= 1.0 else "▼"
            speedup_cell = f"{arrow}{speedup:>6.1f}x"

        if ox_med is None:
            ox_cell = f"{'CRASH':>15}"
            row_cell = f"{'N/A':>6}"
        else:
            ox_cell = f"{ox_med*1000:>13.2f}ms"
            row_cell = f"{ox_rows:>6}"

        print(f"{short:<{COL_W}}  {rl_cell}  {ox_cell}  {speedup_cell}  {row_cell}")

    print("-" * len(header))
    if speedups:
        geo = statistics.geometric_mean(speedups)
        arrow = "▲" if geo >= 1.0 else "▼"
        print(f"{'Geometric mean speedup (comparable queries)':<{COL_W}}  {'':>12}  {'':>15}  {arrow}{geo:>6.1f}x")


# ── main ──────────────────────────────────────────────────────────────────────

def load_world(onto_path_or_url, onto_path_dirs=None):
    w = World()
    if onto_path_dirs:
        for d in onto_path_dirs:
            owlready2.onto_path.append(d)
    w.get_ontology(onto_path_or_url).load()
    return w


def main():
    print("=" * 80)
    print(f"owlready2 SPARQL backend benchmark  |  {REPEATS} repeats, {WARMUP} warm-up")
    print(f"Python: {sys.version.split()[0]}   owlready2: {owlready2.VERSION}")
    print()

    # ── Scenario 1: small built-in test ontology ──────────────────────────────
    print(f"Scenario 1: small test ontology ({SIMPLE_TEST_OWL})")
    print("-" * 80)
    w1 = World()
    owlready2.onto_path.append(os.path.join(ROOT, "test"))
    w1.get_ontology(SIMPLE_TEST_OWL).load()
    triple_count = len(w1.graph)
    build_ms = measure_store_build(w1) * 1000
    print(f"  Triple count: {triple_count}  |  pyoxigraph store build: {build_ms:.2f}ms")
    print()

    r_rl1 = benchmark(w1, make_rdflib_graph, run_rdflib)
    r_ox1 = benchmark(w1, make_ox_graph,     run_ox)
    print_table(r_rl1, r_ox1)
    print()

    # ── Scenario 2: MIE breast-cancer ontology ────────────────────────────────
    if os.path.exists(MIE05):
        print(f"Scenario 2: MIE-05 ontology ({os.path.basename(MIE05)})")
        print("-" * 80)
        w2 = World()
        owlready2.onto_path.append(os.path.abspath(DIST))
        w2.get_ontology(f"file://{os.path.abspath(MIE05)}").load()
        triple_count = len(w2.graph)
        build_ms = measure_store_build(w2) * 1000
        print(f"  Triple count: {triple_count}  |  pyoxigraph store build: {build_ms:.2f}ms")
        print()

        r_rl2 = benchmark(w2, make_rdflib_graph, run_rdflib)
        r_ox2 = benchmark(w2, make_ox_graph,     run_ox)
        print_table(r_rl2, r_ox2)
        print()
    else:
        print(f"Scenario 2 skipped — {MIE05} not found")
        print()


if __name__ == "__main__":
    main()
