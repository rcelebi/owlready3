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

from owlready3 import World, Thing

try:
  import omny
  from omny.store import run_rdflib, run_owlready2
  _HAS_OMNY = True
except ImportError:
  _HAS_OMNY = False


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


if __name__ == "__main__":
  unittest.main()
