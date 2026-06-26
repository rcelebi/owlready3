# -*- coding: utf-8 -*-
# Owlready3
# Copyright (C) 2013-2019 Jean-Baptiste LAMY

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Loose-coupling integration test: Owlready3 <-> omny (https://pypi.org/project/omny/).
#
# omny is a store-agnostic OWL/SPARQL helper; its runners touch only a standard
# rdflib.Graph and World.sparql(), never Owlready3 internals. This test locks in
# that seam. It is skipped unless both `omny` and `rdflib` are installed:
#
#     pip install owlready3[rdflib] omny

import unittest

from owlready3 import World, Thing, ObjectProperty

try:
  import omny
  from omny.store import run_rdflib, run_owlready2
  _HAS_OMNY = True
except ImportError:
  _HAS_OMNY = False

try:
  import rustdl
  from owlready3 import sync_reasoner_rustdl
  _HAS_RUSTDL = True
except ImportError:
  _HAS_RUSTDL = False


def _local(term):
  """Local name of an rdflib term / Owlready entity / IRI string."""
  iri = getattr(term, "iri", None) or str(term)
  return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


@unittest.skipUnless(_HAS_OMNY, "omny not installed (pip install omny)")
class OmnyIntegration(unittest.TestCase):
  BASE = "http://example.org/pizza.owl"

  def setUp(self):
    self.world = World()
    onto = self.world.get_ontology("%s" % self.BASE)
    with onto:
      class Pizza(Thing): pass
      class VegetarianPizza(Pizza): pass
      class Margherita(VegetarianPizza): pass
    self.onto = onto
    self.pizza_iri = "<%s#Pizza>" % self.BASE

  def test_run_rdflib_select(self):
    # omny builds the SPARQL; Owlready3's rdflib bridge executes it.
    q = omny.class_relations_query(self.pizza_iri, construct = False)
    names = { _local(row[0]) for row in run_rdflib(q, self.world.as_rdflib_graph()) }
    self.assertIn("VegetarianPizza", names)   # sub
    self.assertIn("Margherita",      names)   # transitive sub
    self.assertIn("Thing",           names)   # super

  def test_run_rdflib_construct(self):
    q = omny.class_relations_query(self.pizza_iri, construct = True)
    graph = run_rdflib(q, self.world.as_rdflib_graph())
    import rdflib
    self.assertIsInstance(graph, rdflib.Graph)
    self.assertGreater(len(graph), 0)

  def test_run_owlready2_select(self):
    # omny.run_owlready2 routes through World.sparql() (SELECT only).
    q = omny.class_relations_query(self.pizza_iri, construct = False)
    names = { _local(row[0]) for row in run_owlready2(q, self.world) }
    self.assertIn("VegetarianPizza", names)
    self.assertIn("Margherita",      names)

  def test_class_relations_query_accepts_owlready3_object(self):
    # Passing an Owlready3 class works: omny only reads its .iri.
    q = omny.class_relations_query(self.onto.Pizza, construct = False)
    names = { _local(row[0]) for row in run_rdflib(q, self.world.as_rdflib_graph()) }
    self.assertIn("VegetarianPizza", names)


@unittest.skipUnless(_HAS_OMNY and _HAS_RUSTDL,
                     "needs omny + rustdl (pip install omny rustdl)")
class RustdlOmnyIntegration(unittest.TestCase):
  """Reasoner <-> SPARQL seam: omny must surface subsumptions INFERRED by the
  rustdl reasoner, not just asserted triples.

  MargheritaPizza is primitively `hasTopping some CheeseTopping`; CheesyPizza is
  DEFINED as `Pizza and (hasTopping some CheeseTopping)`. The edge
  MargheritaPizza ⊑ CheesyPizza is never asserted — rustdl must derive it, and
  omny's SPARQL must then see it.
  """
  BASE = "http://example.org/pizza_reasoned.owl"

  def setUp(self):
    self.world = World()
    onto = self.world.get_ontology(self.BASE)
    with onto:
      class Pizza(Thing): pass
      class Topping(Thing): pass
      class CheeseTopping(Topping): pass
      class hasTopping(ObjectProperty): pass
      class CheesyPizza(Pizza):
        equivalent_to = [Pizza & hasTopping.some(CheeseTopping)]
      class MargheritaPizza(Pizza):
        is_a = [hasTopping.some(CheeseTopping)]
    self.onto = onto

  def _omny_subs(self, cls):
    q = omny.class_relations_query(cls, relations = ("sub",), construct = False)
    return { _local(row[0]) for row in run_owlready2(q, self.world) }

  def test_subsumption_not_asserted_before_reasoning(self):
    # Without reasoning, the inferred edge must NOT appear.
    self.assertNotIn("MargheritaPizza", self._omny_subs(self.onto.CheesyPizza))

  def test_rustdl_inference_visible_via_omny_select(self):
    with self.onto:
      sync_reasoner_rustdl(self.onto)
    # rustdl infers MargheritaPizza ⊑ CheesyPizza; omny SELECT (World.sparql) sees it.
    self.assertIn("MargheritaPizza", self._omny_subs(self.onto.CheesyPizza))

  def test_rustdl_inference_visible_via_omny_construct(self):
    with self.onto:
      sync_reasoner_rustdl(self.onto)
    q = omny.class_relations_query(self.onto.CheesyPizza, construct = True)
    graph = run_rdflib(q, self.world.as_rdflib_graph())
    import rdflib
    self.assertIsInstance(graph, rdflib.Graph)
    self.assertGreater(len(graph), 0)


if __name__ == "__main__":
  unittest.main()
