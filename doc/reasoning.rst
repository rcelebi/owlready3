Reasoning
=========

OWL reasoners can be used to check the *consistency* of an ontology, and to deduce new fact in the ontology,
typically be *reclassing* Individuals to new Classes, and Classes to new superclasses,
depending on their relations.

Owlready3 performs reasoning with `rustdl <https://github.com/MaastrichtU-IDS/rustdl>`_, a
native Rust OWL 2 DL (SROIQ) reasoner — **no Java Virtual Machine is required**.

rustdl is an optional dependency; install it with::

   pip install owlready3[reasoning]

rustdl supports class subsumption, equivalence, unsatisfiability and individual realization
over the full OWL 2 DL constructs. It does **not** support SWRL rules, inferred
property/data values (``infer_property_values``) or datatype-facet realization — these are
accepted for API compatibility but ignored, with a warning. See :doc:`integration` for the
full reasoning / querying / persistence stack (Owlready3 + rustdl + omny).

The functions ``sync_reasoner_hermit()`` and ``sync_reasoner_pellet()`` remain as deprecated
aliases that delegate to rustdl.


Setting up everything
---------------------

Before performing reasoning, you need to create all Classes, Properties and Instances, and
to ensure that restrictions and disjointnesses / differences have been defined too.

Here is an example creating a 'reasoning-ready' ontology:

::

   >>> from owlready3 import *
   
   >>> onto = get_ontology("http://test.org/onto.owl")
   
   >>> with onto:
   ...     class Drug(Thing):
   ...         def take(self): print("I took a drug")
   
   ...     class ActivePrinciple(Thing):
   ...         pass
   
   ...     class has_for_active_principle(Drug >> ActivePrinciple):
   ...         python_name = "active_principles"

   ...     class Placebo(Drug):
   ...         equivalent_to = [Drug & Not(has_for_active_principle.some(ActivePrinciple))]
   ...         def take(self): print("I took a placebo")

   ...     class SingleActivePrincipleDrug(Drug):
   ...         equivalent_to = [Drug & has_for_active_principle.exactly(1, ActivePrinciple)]
   ...         def take(self): print("I took a drug with a single active principle")
   
   ...     class DrugAssociation(Drug):
   ...         equivalent_to = [Drug & has_for_active_principle.min(2, ActivePrinciple)]
   ...         def take(self): print("I took a drug with %s active principles" % len(self.active_principles))
   
   >>> acetaminophen   = ActivePrinciple("acetaminophen")
   >>> amoxicillin     = ActivePrinciple("amoxicillin")
   >>> clavulanic_acid = ActivePrinciple("clavulanic_acid")
   
   >>> AllDifferent([acetaminophen, amoxicillin, clavulanic_acid])

   >>> drug1 = Drug(active_principles = [acetaminophen])
   >>> drug2 = Drug(active_principles = [amoxicillin, clavulanic_acid])
   >>> drug3 = Drug(active_principles = [])
   
   >>> close_world(Drug)


Running the reasoner
--------------------

The reasoner (rustdl) is simply run by calling the sync_reasoner() global function:

::

   >>> sync_reasoner()

By default, sync_reasoner() places all inferred facts in a special ontology, 'http://inferrences/'.
You can control in which ontology the inferred facts are placed using the 'with ontology' statement
(remember, all triples asserted inside a 'with ontology' statement go inside this ontology).
For example, for placing all inferred facts in the 'onto' ontology:

::

   >>> with onto:
   ...     sync_reasoner()


This allows saving the ontology with the inferred facts (using onto.save() as usual).

The reasoner can also be limited to some ontologies:

::

   >>> sync_reasoner([onto1, onto2,...])

.. note::

   rustdl is a DL classifier: it infers class subsumptions, equivalences and individual
   types, but does **not** materialize inferred object/data property values. The
   ``infer_property_values`` / ``infer_data_property_values`` parameters are therefore
   accepted but ignored (with a warning). For property-value or SWRL-rule inference, use a
   Java reasoner in upstream Owlready2.


Results of the automatic classification
---------------------------------------

Owlready automatically gets the results of the reasoning from rustdl and reclassifies Individuals and Classes,
*i.e* Owlready changes the Classes of Individuals and the superclasses of Classes.

::

   >>> print("drug2 new Classes:", drug2.__class__)
   drug2 new Classes: onto.DrugAssociation
   
   >>> drug1.take()
   I took a drug with a single active principle

   >>> drug2.take()
   I took a drug with 2 active principles

   >>> drug3.take()
   I took a placebo

In this example, drug1, drug2 and drug3 Classes have changed!
The reasoner *deduced* that drug2 is an Association Drug, and that drug3 is a Placebo.

Also notice how the example combines automatic classification of OWL Classes with polymorphism on Python Classes.


Inconsistent classes and ontologies
-----------------------------------

In case of inconsistent ontology, an OwlReadyInconsistentOntologyError is raised.

Inconcistent classes may occur without making the entire ontology inconsistent, as long as these classes have
no individuals. Inconsistent classes are inferred as equivalent to Nothing. They can
be obtained as follows:

::

   >>> list(default_world.inconsistent_classes())

In addition, the consistency of a given class can be tested by checking for Nothing in its equivalent classes,
as follows:

::

   >>> if Nothing in Drug.equivalent_to:
   ...       print("Drug is inconsistent!")

   

Querying inferred classification
--------------------------------

The .get_parents_of(), .get_instances_of() and .get_children_of() methods of an ontology can be used to query the
hierarchical relations, limited to those defined in the given ontology. This is commonly used after reasoning,
to obtain the inferred hierarchical relations.

 * .get_parents_of(entity) accepts any entity (Class, property or individual), and returns
   the superclasses (for a class), the superproperties (for a property), or the classes (for an individual).
   (NB for obtaining all parents, independently of the ontology they are asserted in, use entity.is_a).
 * .get_instances_of(Class) returns the individuals that are asserted as belonging to the given Class in the ontology.
   (NB for obtaining all instances, independently of the ontology they are asserted in, use Class.instances()).
 * .get_children_of(entity) returns the subclasses (or subproperties) that are asserted for the given Class
   or property in the ontology.
   (NB for obtaining all children, independently of the ontology they are asserted in, use entity.subclasses()).

Here is an example:

::

   >>> inferences = get_ontology("http://test.org/onto_inferences.owl")
   >>> with inferences:
   ...     sync_reasoner()
   
   >>> inferences.get_parents_of(drug1)
   [onto.SingleActivePrincipleDrug]
   
   >>> drug1.is_a
   [onto.has_for_active_principle.only(OneOf([onto.acetaminophen])), onto.SingleActivePrincipleDrug]
   
