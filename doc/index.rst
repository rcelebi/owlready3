Welcome to Owlready3's documentation!
*************************************

Owlready3 is a lightweight package for ontology-oriented programming in Python. It can load
OWL 2.0 ontologies as Python objects, modify them, save them, and perform reasoning via the
native **rustdl** OWL 2 DL reasoner (no Java required). Owlready3 allows a transparent access
to OWL ontologies (contrary to usual Java-based API).

Owlready3 includes an optimized triplestore / quadstore, based on SQLite3, optimized for
performance and memory consumption. It is a slimmed-down fork of Owlready2 designed to be
**loosely coupled** with external tools: reasoning via rustdl, and persistence / SPARQL
querying via the rdflib bridge and `omny <https://pypi.org/project/omny/>`_ — see
:doc:`integration`.

Owlready3 has been created at the LIMICS reseach lab,
University Paris 13, Sorbonne Paris Cité, INSERM UMRS 1142, Paris 6 University, by
Jean-Baptiste Lamy. It was initially developed during the VIIIP research project funded by ANSM,
the French Drug Agency;
this is why some examples in this documentation relate to drug ;).

Owlready3 is available under the GNU LGPL licence v3.
If you use Owlready3 in scientific works, **please cite the following article**:

   **Lamy JB**.
   `Owlready: Ontology-oriented programming in Python with automatic classification and high level constructs for biomedical ontologies. <http://www.lesfleursdunormal.fr/_downloads/article_owlready_aim_2017.pdf>`_
   **Artificial Intelligence In Medicine 2017**;80:11-28
   
In case of troubles, questions or comments, please use this Forum/Mailing list: http://owlready.8326.n8.nabble.com


Table of content
----------------

.. toctree::
   intro.rst
   install.rst
   onto.rst
   class.rst
   properties.rst
   datatype.rst
   restriction.rst
   disjoint.rst
   mixing_python_owl.rst
   reasoning.rst
   integration.rst
   annotations.rst
   namespace.rst
   world.rst
   manchester.rst
   rule.rst
   porting1.rst
   contact.rst
