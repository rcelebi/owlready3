# Owlready2 — pyoxigraph fork

This is a fork of [Owlready2](https://bitbucket.org/jibalamy/owlready2) that replaces the RDFlib SPARQL adapter with a [pyoxigraph](https://github.com/oxigraph/oxigraph) backend, adding a persistent RDF quad-store and three distinct query paths optimised for different use cases.

---

## Backends

Use `backend="oxigraph"` to activate the pyoxigraph store.  The default `backend="sqlite"` (triplelite) is unchanged.

```python
from owlready2 import *

# Persistent file-backed store (RocksDB + SQLite shadow)
world = World(backend="oxigraph", filename="/data/snomed.owlox")
onto  = world.get_ontology("file:///data/snomed.owl").load()

# In-memory (no persistence)
world = World(backend="oxigraph")
```

| Backend | Store file | SPARQL engine | Writes |
|---------|-----------|---------------|--------|
| `sqlite` (default) | `*.sqlite3` (SQLite) | rdflib (slow) or pyoxigraph rebuild | via SQLite |
| `oxigraph` | `*.owlox/` (RocksDB) + `*.owlox.sqlite3` (shadow) | pyoxigraph (fast) | directly to RocksDB |

---

## Query paths

There are **three independent query paths**. Choosing the right one is the key performance decision.

### 1 — Raw SPARQL (`graph.query()`)

Executes SPARQL directly against the pyoxigraph store.  Returns raw `pyoxigraph.NamedNode` / `Literal` / `BlankNode` objects — **no owlready2 conversion**.

```python
g = world.as_sparql_graph()
g.bind("owl",  "http://www.w3.org/2002/07/owl#")
g.bind("rdfs", "http://www.w3.org/2000/01/rdf-schema#")

# yields tuples of raw pyoxigraph terms
for (cls,) in g.query("SELECT ?c WHERE { ?c a owl:Class }"):
    print(cls.value)          # IRI string
```

**Use when:** you need SPARQL results as strings/IRIs without caring about owlready2 objects.  
**Cost:** SPARQL parse + plan + scan — no Python object construction.

---

### 2 — SPARQL with owlready2 conversion (`graph.query_owlready()`)

Same SPARQL execution, but every result term is resolved to an owlready2 Python object (`ThingClass`, `Individual`, `str`, etc.) via the IRI→storid→entity lookup chain.

```python
for (cls,) in g.query_owlready("SELECT ?c WHERE { ?c a owl:Class }"):
    print(cls.name)           # owlready2 class object
    print(cls.label)          # annotation property access
```

**Use when:** you need to work with owlready2 objects after the query (e.g. navigate `is_a`, call Python methods, read annotation properties).  
**Cost:** SPARQL cost + per-term IRI→object resolution (dict lookup or SQL batch, cached in `_entity_cache`).

#### Internal split

`query_owlready()` delegates to two separated internal methods, callable individually:

```python
raw_result = g._query_raw("SELECT ?c WHERE { ?c a owl:Class }")
# raw_result is a pyoxigraph QuerySolutions object

python_rows = g._convert_rows(raw_result)
# python_rows is [[owlready2_object, ...], ...]
```

---

### 3 — owlready2 Python API (SQLite-backed)

Class hierarchy traversal, annotation access, and `world.search()` always route through owlready2's internal **SQLite shadow** (`triplelite`), never through pyoxigraph.

```python
# Direct subclasses — pure SQL, sub-millisecond
for sub in onto.ClinicalFinding.subclasses():
    print(sub.name)

# Transitive descendants — recursive SQL CTE
for cls in onto.ClinicalFinding.descendants():
    print(cls.name)

# Full-text annotation search
results = world.search(label="*fracture*")

# Manchester / DL expressions — owlready2 class constructs
from owlready2 import *
expr = onto.FindingSite.some(owl.Thing) & onto.ClinicalFinding
matching = list(expr.subclasses())
```

**Use when:** navigating the class hierarchy, accessing annotations, or building OWL class expressions.  
**Cost:** SQLite queries — fast for direct lookups, slower for full transitive traversal of very large hierarchies.

---

## Architecture overview

```
World
├── graph (TripleOxigraph)          ← pyoxigraph Store (RocksDB, persistent)
│   ├── _store                      ← pyoxigraph.Store  (live, always current)
│   └── _db (SQLite shadow)         ← triplelite schema  (IRI ↔ storid mapping,
│                                      obj/data triple tables for owlready2 SQL ops)
│
└── as_sparql_graph() → OxigraphGraph
    ├── query(sparql)               ← path 1: raw pyoxigraph terms
    ├── query_owlready(sparql)      ← path 2: owlready2 Python objects
    │   ├── _query_raw()            ←   executes SPARQL on pyoxigraph store
    │   └── _convert_rows()         ←   IRI → owlready2 entity resolution
    └── (Python API calls)          ← path 3: SQL on SQLite shadow
```

### Why two stores?

| Store | Role |
|-------|------|
| **pyoxigraph (RocksDB)** | SPARQL engine — fast pattern matching, arbitrary SPARQL queries |
| **SQLite shadow** | owlready2 internals — SQL joins for hierarchy traversal, IRI↔storid mapping, annotations |

The SQLite shadow is **not** a backup of pyoxigraph.  It stores the same triples but in a relational schema that owlready2's Python API depends on (recursive CTEs for transitivity, GROUP BY for cardinality, etc.).  These cannot be replaced by RocksDB without rewriting owlready2's core.

### Write paths

| Operation | Goes to |
|-----------|---------|
| owlready2 Python API (`cls.is_a =`, `cls.label =`) | SQLite shadow → `_invalidate_cache()` |
| `graph.update(sparql_update)` (oxigraph backend) | pyoxigraph directly (no SQLite sync, no diff) |
| `graph.update(sparql_update)` (sqlite backend) | in-memory copy → before/after diff → SQLite |

---

## SPARQL UPDATE behaviour

With the `oxigraph` backend, SPARQL UPDATEs go directly to the live pyoxigraph store — no expensive before/after diff:

```python
g.update("""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    INSERT DATA { <http://example.org/NewClass> a owl:Class }
""")
# Immediately visible to subsequent g.query() and g.query_owlready() calls.
# SQLite shadow is NOT updated — owlready2 Python API will not see the new class.
```

If you need the change to be visible via the owlready2 Python API, use the owlready2 API to write instead:

```python
with onto:
    class NewClass(owl.Thing): pass
# SQLite shadow is updated; pyoxigraph store is updated via _rebuild on next query.
```

---

## Context graphs

Each ontology maps to a named graph inside the pyoxigraph store.  You can scope queries or updates to a single ontology:

```python
ctx = g.get_context(onto)           # OxigraphContextGraph
ctx.query_owlready("SELECT ...")    # query scoped to this ontology's named graph
ctx.update("INSERT DATA { ... }")   # update routed to this ontology's graph
```

---

## Performance notes (SNOMED CT, ~2M triples)

| Operation | Implementation | Typical time |
|-----------|---------------|--------------|
| All `owl:Class` (364 k rows) | raw SPARQL | ~470 ms |
| Direct subclasses of a class | owlready2 Python API | < 1 ms |
| Transitive descendants (41 k) | owlready2 Python API | ~2.9 s |
| Transitive descendants (41 k) | SPARQL (recursive) | ~250 ms |
| Single rdfs:label lookup | raw SPARQL | ~0.03 ms |
| SPARQL UPDATE (100 triples, batch) | pyoxigraph direct | ~0.2 ms |
| Rebuild pyoxigraph from NT file (cold) | bulk_load | ~2.3 s |
| Re-open cached store | RocksDB mmap | ~0.04 ms |

The `oxigraph` backend avoids the rebuild cost on re-open: both the RocksDB store and the SQLite shadow are file-backed and loaded directly.

---

## Key files

| File | Purpose |
|------|---------|
| `owlready2/tripleoxigraph.py` | `TripleOxigraph` — the quadstore backend; wraps pyoxigraph Store + SQLite shadow |
| `owlready2/pyoxigraph_store.py` | `OxigraphGraph` — SPARQL interface; the three query paths live here |
| `owlready2/namespace.py` | `World.set_backend()` — wires `backend="oxigraph"` to `TripleOxigraph` |
| `benchmark_snomed.py` | Full benchmark across all query paths at SNOMED scale |
