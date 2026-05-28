Manchester OWL Syntax
=====================

Owlready2 includes support for the `Manchester OWL syntax
<https://www.w3.org/TR/owl2-manchester-syntax/>`_ via the ``owlready2.manchester``
module. It provides serialisation, parsing, and query helpers.

The module is automatically activated when imported:

::

   >>> from owlready2.manchester import (
   ...     to_manchester, parse_manchester_expression,
   ...     classes_matching, instances_of,
   ...     manchester_render_ontology, parse_manchester_ontology,
   ... )


Serialising class expressions to Manchester syntax
--------------------------------------------------

``to_manchester(expr, prefixes=None)`` converts any Owlready2 class expression
to a Manchester string:

::

   >>> from owlready2 import *
   >>> from owlready2.manchester import to_manchester
   >>>
   >>> onto = get_ontology("http://example.org/onto/")
   >>> with onto:
   ...     class Pizza(Thing): pass
   ...     class hasTopping(Pizza >> Thing): pass
   ...     class MeatTopping(Thing): pass
   ...     class VegetarianPizza(Pizza):
   ...         equivalent_to = [Pizza & hasTopping.only(Not(MeatTopping))]
   >>>
   >>> to_manchester(VegetarianPizza.equivalent_to[0])
   'Pizza and (hasTopping only (not MeatTopping))'

An optional ``prefixes`` dict maps namespace IRIs to short prefixes for more
readable output:

::

   >>> to_manchester(VegetarianPizza.equivalent_to[0],
   ...              prefixes={"http://example.org/onto/": "onto:"})
   'onto:Pizza and (onto:hasTopping only (not onto:MeatTopping))'


Parsing Manchester expressions
-------------------------------

``parse_manchester_expression(text, ontology, prefixes=None)`` parses a
Manchester string into an Owlready2 class expression:

::

   >>> from owlready2.manchester import parse_manchester_expression
   >>> expr = parse_manchester_expression(
   ...     "Pizza and (hasTopping some MeatTopping)", onto)
   >>> expr
   Pizza and hasTopping some MeatTopping

The optional ``prefixes`` dict maps short prefixes to namespace IRIs:

::

   >>> expr = parse_manchester_expression(
   ...     "p:Pizza and (p:hasTopping some p:MeatTopping)", onto,
   ...     prefixes={"p": "http://example.org/onto/"})


Rendering and parsing full ontologies (.omn files)
--------------------------------------------------

``manchester_render_ontology(onto)`` serialises an entire ontology to a
Manchester ``.omn`` string:

::

   >>> from owlready2.manchester import manchester_render_ontology
   >>> omn_text = manchester_render_ontology(onto)
   >>> print(omn_text)

``parse_manchester_ontology(source, ontology)`` loads a ``.omn`` file into an
existing ontology. ``source`` can be a file path or a file-like object:

::

   >>> from owlready2.manchester import parse_manchester_ontology
   >>> parse_manchester_ontology("my_ontology.omn", onto)


TBox search: finding classes by structural pattern
--------------------------------------------------

``classes_matching(expr_str, ontology)`` finds classes whose axioms contain a
given class expression as a structural sub-pattern. This is a TBox query — it
searches the class hierarchy, not individuals:

::

   >>> from owlready2.manchester import classes_matching
   >>> # Find all classes that have a someValuesFrom restriction on hasTopping
   >>> matches = classes_matching("hasTopping some Thing", onto)
   >>> print(matches)
   [pizza_onto.NonVegetarianPizza, ...]

The ``expr_str`` is parsed as a Manchester expression and matched structurally
against the ``is_a`` and ``equivalent_to`` axioms of every class in the
ontology.


ABox query: finding individuals by class membership
----------------------------------------------------

``instances_of(cls, direct=False)`` returns individuals that are classified
under ``cls``. When ``direct=False`` (default) it includes indirect membership
via subclasses:

::

   >>> from owlready2.manchester import instances_of
   >>> instances_of(VegetarianPizza)
   [onto.my_veggie_pizza]

Set ``direct=True`` to restrict results to individuals whose most specific
inferred type is exactly ``cls``:

::

   >>> instances_of(VegetarianPizza, direct=True)

.. note::

   ``instances_of`` relies on inferred class memberships. Run
   ``sync_reasoner()`` before calling it to get results that include
   classification by the reasoner.


World-level shortcut
--------------------

After importing ``manchester``, the world gains a convenience method:

::

   >>> default_world.manchester_query("hasTopping some MeatTopping")

This is equivalent to ``classes_matching(expr_str, onto)`` scoped to all
ontologies in ``default_world``.
