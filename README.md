# Owlready3 — lightweight Owlready2 fork (rustdl reasoner)

Owlready3 is a slimmed-down fork of [Owlready2](https://bitbucket.org/jibalamy/owlready2)
focused on **in-memory manipulation of small / mid-range OWL & RDF ontologies** as Python
objects: load, edit, query and save OWL 2.0 in RDF/XML, N-Triples and OWL/XML, with the
optimized SQLite quad-store (`triplelite`) and the Cython parser retained from upstream.

It is designed to be **loosely coupled** with best-of-breed external tools rather than
bundling everything:

| Concern | Tool | How it plugs in |
|---|---|---|
| In-memory OWL/RDF model, load/save, edit | **Owlready3** (this package, zero hard deps) | — |
| Reasoning (classification, realization) | **[rustdl](https://github.com/MaastrichtU-IDS/rustdl)** (native Rust OWL 2 DL) | `sync_reasoner()`; install `owlready3[reasoning]` |
| Persistent store + SPARQL querying | **omny** (and any RDF/SPARQL backend) | over the rdflib bridge; install `owlready3[rdflib]` |

Compared with upstream Owlready2 this fork **removes** the bundled Java reasoners
(HermiT/Pellet), the pyoxigraph backend, PyMedTermino2 and the Streamlit UI, and **replaces**
Java reasoning with rustdl.

## Installation

```bash
pip install owlready3                 # core only — no third-party dependencies
pip install owlready3[reasoning]      # + rustdl  (enables sync_reasoner)
pip install owlready3[rdflib]         # + rdflib  (enables as_rdflib_graph / sparql)
pip install owlready3[all]            # rustdl + rdflib
```

Reasoning and the rdflib bridge are optional backends: the core imports and runs without
them, and each raises a clear "install the extra" error only when you actually use it.

## Core usage

```python
from owlready3 import *

world = World()
onto  = world.get_ontology("http://example.org/pizza.owl")
with onto:
    class Pizza(Thing): pass
    class VegetarianPizza(Pizza): pass
    class Margherita(VegetarianPizza): pass

onto.save(file="pizza.owl", format="rdfxml")     # or "ntriples"
```

(The examples below reuse this `world` / `onto`.)

## Reasoning — via rustdl (`owlready3[reasoning]`)

`sync_reasoner()` exports the world to OWL Functional Syntax and runs the native
[rustdl](https://github.com/MaastrichtU-IDS/rustdl) reasoner; inferred subsumptions,
equivalences, unsatisfiable classes and individual types are applied back onto the
quad-store and the loaded Python objects.

```python
with onto:
    sync_reasoner(world)          # rustdl; no JVM required

list(Margherita.is_a)             # reparented to inferred superclasses
```

`sync_reasoner_hermit` / `sync_reasoner_pellet` remain as deprecated aliases that delegate
to rustdl. Note rustdl is a DL classifier: SWRL rules, inferred property/data values and
datatype-facet realization are **not** supported.

## SPARQL & persistence — via the rdflib bridge (`owlready3[rdflib]`)

`World.as_rdflib_graph()` returns a standard `rdflib.Graph` backed by the live quad-store,
and `World.sparql()` runs SPARQL through rdflib's engine:

```python
rows = world.sparql("SELECT ?s WHERE { ?s a owl:Class }")   # -> list of owlready3 objects
ok   = world.sparql("ASK { <...#Margherita> rdfs:subClassOf <...#Pizza> }")  # -> bool
with onto:
    world.sparql("INSERT DATA { <...#Calzone> a owl:Class }")                # UPDATE
```

`sparql()` returns: SELECT → rows of owlready3 entities; ASK → `bool`;
CONSTRUCT/DESCRIBE → an `rdflib.Graph`; UPDATE → writes to the store.

### Using omny for querying

[omny](https://pypi.org/project/omny/) is a store-agnostic OWL/SPARQL helper. It only
touches the standard `rdflib.Graph` / `World.sparql()` interfaces — never Owlready3's
internals — so the coupling is purely through RDF:

```python
import omny
from omny.store import run_rdflib

g = world.as_rdflib_graph()
q = omny.class_relations_query("<http://example.org/pizza.owl#Pizza>", construct=False)  # SELECT
run_rdflib(q, g)               # execute against Owlready3's live rdflib graph
# default construct=True builds a CONSTRUCT query; run_rdflib then returns an rdflib.Graph
```

(omny's `run_owlready2(q, world)` also works — it calls `world.sparql()`, which in Owlready3
is itself the rdflib bridge, so it's equivalent to `run_rdflib(q, world.as_rdflib_graph())`.)

For a **persistent** store, export to RDF and load it into omny's backend of choice (e.g.
pyoxigraph), or point omny at a SPARQL endpoint — Owlready3 stays the in-memory editing
layer and hands data over as standard RDF:

```python
import io, pyoxigraph, omny
from omny.store import run_pyoxigraph

# 1. Owlready3 serialises standard RDF to memory (no temp file)
#    (call sync_reasoner(world) first to also export rustdl's inferred triples)
buf = io.BytesIO()
world.save(buf, format="ntriples")

# 2. Bulk-load it into a persistent (on-disk) pyoxigraph store
store = pyoxigraph.Store("pizza_store")                       # RocksDB dir; reopens instantly
store.bulk_load(buf.getvalue(), format=pyoxigraph.RdfFormat.N_TRIPLES)

# 3. omny queries the persistent store (no Owlready3 needed at query time)
q = omny.class_relations_query("<http://example.org/pizza.owl#Pizza>", construct=False)
for sol in run_pyoxigraph(q, store):
    print(sol["rel"])        # VegetarianPizza, Margherita, Thing, ...
```

For a remote endpoint, use `omny.store.run_endpoint(q, "https://example.org/sparql")` instead;
either way Owlready3 only ever produces/consumes standard RDF.

## Relationship to upstream Owlready2

Owlready3 tracks Owlready2's package shape (flat layout, `triplelite` quad-store, Cython
parser, Manchester syntax, `close_world`) so that upstream fixes remain mergeable. The
divergences are: package/import name `owlready3`, the rustdl reasoner, the removed
backends/modules listed above, and the optional-backend dependency model.

## Key files

| File | Purpose |
|---|---|
| `reasoning.py` | `sync_reasoner_rustdl` — exports OFN, drives rustdl, applies inferences |
| `fs_render.py` | World → OWL Functional Syntax serializer (for rustdl) |
| `rdflib_store.py` | `TripleLiteRDFlibStore` — rdflib bridge over the quad-store |
| `namespace.py` | `World` — `as_rdflib_graph()`, `sparql()`, backends |
| `triplelite.py` | the optimized SQLite quad-store |
