Integrating Owlready3 with rustdl and omny
==========================================

Owlready3 is deliberately a **lightweight, in-memory OWL/RDF toolkit**: it loads, edits and
saves ontologies as Python objects. Heavier concerns are delegated to loosely-coupled,
**optional** backends, so the core has no third-party dependencies:

==========================  =========================================  =============================================
Concern                     Tool                                       How it plugs in
==========================  =========================================  =============================================
Manipulate OWL/RDF          **Owlready3** (this package)               built in
Reasoning                   **rustdl** (native Rust OWL 2 DL)          ``sync_reasoner()`` — ``owlready3[reasoning]``
Persistent store + SPARQL   **omny** (+ any RDF/SPARQL backend)        the rdflib bridge — ``owlready3[rdflib]``
==========================  =========================================  =============================================

Each backend is imported lazily and only when used; if it is missing you get a clear message
telling you which extra to install.


Installation
------------

::

   pip install owlready3                 # core only (no third-party deps)
   pip install owlready3[reasoning]      # + rustdl   -> sync_reasoner()
   pip install owlready3[rdflib]         # + rdflib   -> as_rdflib_graph() / sparql()
   pip install owlready3[all]            # rustdl + rdflib
   pip install omny                      # the OWL/SPARQL query helper (separate package)


Reasoning with rustdl
---------------------

``sync_reasoner()`` serialises the world to OWL Functional Syntax and runs the native
`rustdl <https://github.com/MaastrichtU-IDS/rustdl>`_ reasoner — **no Java / JVM required**.
Inferred class subsumptions, equivalences, unsatisfiable classes (made equivalent to
``owl:Nothing``) and individual types are applied back onto the quad-store and the loaded
Python objects, just like the previous HermiT/Pellet integration.

.. code-block:: python

   from owlready3 import *

   onto = get_ontology("http://example.org/drug.owl")
   with onto:
       class Drug(Thing): pass
       class ActivePrinciple(Thing): pass
       class has_for_active_principle(Drug >> ActivePrinciple): pass
       class SingleActivePrincipleDrug(Drug):
           equivalent_to = [Drug & has_for_active_principle.exactly(1, ActivePrinciple)]

       my_drug = Drug(has_for_active_principle = [ActivePrinciple()])

   with onto:
       sync_reasoner()                       # rustdl

   print(my_drug.__class__)                  # -> SingleActivePrincipleDrug (realized)

``sync_reasoner_hermit`` / ``sync_reasoner_pellet`` remain as deprecated aliases that
delegate to rustdl.

**What rustdl supports:** class classification and individual realization over the full
OWL 2 DL (SROIQ) constructs, including complex class expressions (intersection, union,
complement, restrictions, cardinality, nominals).

**What it does not:** SWRL rule reasoning, inferred *property/data values*
(``infer_property_values``) and datatype-facet realization. These are accepted for API
compatibility but ignored (with a warning). If you need them, keep using a Java reasoner
in upstream Owlready2.


Querying and persistence with omny
----------------------------------

`omny <https://pypi.org/project/omny/>`_ is a store-agnostic OWL/SPARQL helper. It builds
SPARQL queries (e.g. ``omny.class_relations_query``) and runs them against whatever store
you give it (``omny.store.run_rdflib``, ``run_pyoxigraph``, ``run_owlready2``,
``run_endpoint``).

The integration is **purely through RDF/SPARQL** — omny only ever touches a standard
``rdflib.Graph`` or ``World.sparql()``, never Owlready3's internals. Owlready3 exposes both:

* ``World.as_rdflib_graph()`` — a live ``rdflib.Graph`` backed by the quad-store.
* ``World.sparql(query, params=None)`` — SPARQL via rdflib's engine; SELECT returns rows of
  Owlready3 objects, ASK returns ``bool``, CONSTRUCT/DESCRIBE return an ``rdflib.Graph``,
  UPDATE writes to the store.

In-memory querying (the live graph)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import omny
   from omny.store import run_rdflib

   g = world.as_rdflib_graph()

   # omny builds the SPARQL; run_rdflib executes it against the live graph.
   # construct=False -> a SELECT query:
   q = omny.class_relations_query("<http://example.org/pizza.owl#Pizza>", construct = False)
   rows = run_rdflib(q, g)                     # SELECT -> list of rows

   # construct=True (the default) -> a CONSTRUCT query; run_rdflib returns an rdflib.Graph:
   subgraph = run_rdflib(omny.class_relations_query("<http://example.org/pizza.owl#Pizza>"), g)

``omny.class_relations_query`` also accepts an Owlready3 class directly (it reads ``.iri``):

.. code-block:: python

   q = omny.class_relations_query(onto.Pizza)

.. note::

   omny also offers ``run_owlready2(query, world)``, which runs the query via
   ``world.sparql()`` (SELECT only). It works with Owlready3, but note that here
   ``World.sparql()`` is itself implemented on the rdflib bridge, so
   ``run_owlready2(q, world)`` and ``run_rdflib(q, world.as_rdflib_graph())`` use the
   same engine and return the same results. (In upstream Owlready2, ``run_owlready2``
   would instead use Owlready2's native SPARQL-to-SQL engine — a distinct query path.)

Persistent store
~~~~~~~~~~~~~~~~~

Owlready3 stays the in-memory editing layer and hands data over as **standard RDF**. For a
persistent triplestore, export and load into omny's backend of choice (e.g. pyoxigraph),
or point omny at a SPARQL endpoint:

.. code-block:: python

   import io, pyoxigraph, omny
   from omny.store import run_pyoxigraph

   buf = io.BytesIO()                                               # serialise RDF to memory
   world.save(buf, format = "ntriples")                            #   (no temp file)

   store = pyoxigraph.Store("ontology_store")                       # persistent RocksDB dir
   store.bulk_load(buf.getvalue(), format = pyoxigraph.RdfFormat.N_TRIPLES)   # optimized bulk ingest

   q = omny.class_relations_query("<http://example.org/pizza.owl#Pizza>", construct = False)
   for sol in run_pyoxigraph(q, store):                             # query the persistent store
       print(sol["rel"])

For a remote triplestore, point omny at a SPARQL endpoint instead::

   omny.store.run_endpoint(q, "https://example.org/sparql")

Persisting the *reasoned* graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the reasoner **before** exporting, and the saved RDF carries the inferred triples
(subsumptions, class assertions, …) alongside the asserted ones — so the persistent store,
and any omny query against it, see the materialised result with no reasoner needed at query
time:

.. code-block:: python

   import io, pyoxigraph, omny
   from owlready3 import *
   from omny.store import run_pyoxigraph

   world = World()
   onto  = world.get_ontology("http://example.org/pizza.owl")
   with onto:
       class Topping(Thing): pass
       class Meat(Topping): pass
       class Cheese(Topping): pass
       class has_topping(Thing >> Topping): pass
       AllDisjoint([Meat, Cheese])
       class Pizza(Thing): pass
       class VegetarianPizza(Pizza):
           equivalent_to = [Pizza & Not(has_topping.some(Meat))]
       class VegetalianPizza(Pizza):                       # vegetarian and no cheese
           equivalent_to = [Pizza & Not(has_topping.some(Meat)) & Not(has_topping.some(Cheese))]

   with onto:
       sync_reasoner(world)                                # infers VegetalianPizza ⊑ VegetarianPizza

   buf = io.BytesIO()                                      # asserted + inferred triples,
   world.save(buf, format="ntriples")                      #   serialised to memory

   store = pyoxigraph.Store("pizza_store")                 # persistent, on-disk
   store.bulk_load(buf.getvalue(), format=pyoxigraph.RdfFormat.N_TRIPLES)

   q = omny.class_relations_query("<http://example.org/pizza.owl#VegetarianPizza>", construct=False)
   print(sorted(str(sol["rel"]) for sol in run_pyoxigraph(q, store)))
   # -> includes VegetalianPizza, which rustdl inferred (it was never asserted)

By default ``sync_reasoner()`` records inferences in a dedicated ``http://inferrences/``
ontology; calling it inside ``with onto:`` instead records them in ``onto``. Either way
``world.save()`` exports the whole world, so the inferred triples are included.


End-to-end: manipulate, reason, query
-------------------------------------

.. code-block:: python

   from owlready3 import *
   import omny
   from omny.store import run_rdflib

   # 1. Manipulate (Owlready3)
   world = World()
   onto  = world.get_ontology("http://example.org/pizza.owl")
   with onto:
       class Pizza(Thing): pass
       class Cheese(Thing): pass
       class has_topping(Pizza >> Thing): pass
       class CheesyPizza(Pizza):
           equivalent_to = [Pizza & has_topping.some(Cheese)]
       p = Pizza(has_topping = [Cheese()])

   # 2. Reason (rustdl) — pass `world` since we created an explicit World()
   with onto:
       sync_reasoner(world)
   assert CheesyPizza in p.__class__.ancestors()      # realized as a CheesyPizza

   # 3. Query (omny over the rdflib bridge)
   q = omny.class_relations_query(onto.CheesyPizza)
   for row in run_rdflib(q, world.as_rdflib_graph()):
       print(row)


Notes and limitations
----------------------

* **rustdl is a DL classifier**, not a rule engine — see the reasoning limitations above.
* **rdflib's SPARQL engine** is flexible (paths, ASK, CONSTRUCT, UPDATE) but slower than a
  native SPARQL-to-SQL engine on very large stores; for big data, hand the triples to a
  dedicated store (pyoxigraph / an endpoint) and query there via omny.
* omny's *Manchester* parse/render functions target ``owlready2`` objects and are **not**
  needed with Owlready3, which has its own Manchester support (see :doc:`manchester`). The
  store/query functions used above are object-agnostic and work unchanged.

A runnable integration test lives at ``test/test_integration_omny.py`` (skipped unless
``omny`` is installed).
