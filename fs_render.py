# -*- coding: utf-8 -*-
# Owlready3
# Copyright (C) 2013-2019 Jean-Baptiste LAMY
# LIMICS (Laboratoire d'informatique médicale et d'ingénierie des connaissances en santé), UMR_S 1142
# University Paris 13, Sorbonne paris-Cité, Bobigny, France

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

# Serialize an Owlready World / Ontology to OWL 2 Functional-Style Syntax (.ofn).
#
# This exists because the rustdl reasoner's RDF/XML reader does not reconstruct
# some nested anonymous class expressions (e.g. ObjectComplementOf around an
# ObjectSomeValuesFrom), whereas its Functional-Syntax reader is complete.
# Owlready only writes RDF/XML and N-Triples natively, so we emit Functional
# Syntax here and feed that to rustdl.

import owlready3
from owlready3.base            import *
from owlready3.base            import _universal_datatype_2_abbrev
from owlready3.prop            import *
from owlready3.entity          import ThingClass
from owlready3.namespace       import CURRENT_NAMESPACES
from owlready3.class_construct import Not, Inverse, And, Or, Restriction, OneOf, PropertyChain, ConstrainedDatatype, _PY_FACETS


_XSD = "http://www.w3.org/2001/XMLSchema#"

_BUILTIN_NS = (
  "http://www.w3.org/2002/07/owl#",
  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
  "http://www.w3.org/2000/01/rdf-schema#",
  _XSD,
)

# Restriction cardinality keyword (Min/Max/Exact) per owlready restriction type.
_CARD_KEYWORD = { MIN: "MinCardinality", MAX: "MaxCardinality", EXACTLY: "ExactCardinality" }

# ConstrainedDatatype facet attribute -> xsd facet IRI local name.
_FACET_IRI = {
  "min_inclusive"   : "minInclusive",
  "max_inclusive"   : "maxInclusive",
  "min_exclusive"   : "minExclusive",
  "max_exclusive"   : "maxExclusive",
  "length"          : "length",
  "min_length"      : "minLength",
  "max_length"      : "maxLength",
  "pattern"         : "pattern",
  "total_digits"    : "totalDigits",
  "fraction_digits" : "fractionDigits",
}


def _is_builtin_iri(iri):
  return any(iri.startswith(ns) for ns in _BUILTIN_NS)


class _FunctionalSyntaxExporter:
  def __init__(self, world):
    self.world = world
    self.lines = []

  # ---- low-level helpers -------------------------------------------------

  def _iri(self, entity):
    return "<%s>" % entity.iri

  @staticmethod
  def _escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

  def _datatype_iri(self, datatype):
    # datatype is a Python type (int, str, …) or an owlready datatype entity.
    abbrev = _universal_datatype_2_abbrev.get(datatype)
    if abbrev is not None:
      return "<%s>" % self.world._unabbreviate(abbrev)
    iri = getattr(datatype, "iri", None)
    if iri: return "<%s>" % iri
    return "<%sstring>" % _XSD

  def _literal(self, value):
    # Language-tagged string (owlready locstr carries a .lang attribute).
    lang = getattr(value, "lang", None)
    if lang:
      return '"%s"@%s' % (self._escape(str(value)), lang)
    if isinstance(value, bool):
      return '"%s"^^<%sboolean>' % ("true" if value else "false", _XSD)
    if isinstance(value, int):
      return '"%d"^^<%sinteger>' % (value, _XSD)
    if isinstance(value, float):
      return '"%r"^^%s' % (value, self._datatype_iri(float))   # owlready maps float -> xsd:decimal
    if isinstance(value, str):
      return '"%s"^^<%sstring>' % (self._escape(value), _XSD)
    return '"%s"^^%s' % (self._escape(str(value)), self._datatype_iri(type(value)))

  # ---- property / class / datatype expressions ---------------------------

  def _property_expr(self, prop):
    if isinstance(prop, Inverse):
      return "ObjectInverseOf(%s)" % self._iri(prop.property)
    return self._iri(prop)

  def _data_range(self, dr):
    if isinstance(dr, ConstrainedDatatype):
      facets = []
      for attr in _PY_FACETS:
        if attr in dr.__dict__ and attr in _FACET_IRI:
          facets.append("<%s%s> %s" % (_XSD, _FACET_IRI[attr], self._literal(dr.__dict__[attr])))
      return "DatatypeRestriction(%s %s)" % (self._datatype_iri(dr.base_datatype), " ".join(facets))
    return self._datatype_iri(dr)

  def _concept(self, c):
    if isinstance(c, ThingClass):           return self._iri(c)
    if isinstance(c, And):                  return "ObjectIntersectionOf(%s)" % " ".join(self._concept(x) for x in c.Classes)
    if isinstance(c, Or):                   return "ObjectUnionOf(%s)"        % " ".join(self._concept(x) for x in c.Classes)
    if isinstance(c, Not):                  return "ObjectComplementOf(%s)"   % self._concept(c.Class)
    if isinstance(c, OneOf):                return "ObjectOneOf(%s)"          % " ".join(self._iri(i) for i in c.instances)
    if isinstance(c, Restriction):          return self._restriction(c)
    if isinstance(c, Inverse):              return self._property_expr(c)
    # A bare datatype used where a class is expected (data ranges).
    if c in _universal_datatype_2_abbrev:   return self._datatype_iri(c)
    if isinstance(c, ConstrainedDatatype):  return self._data_range(c)
    return self._iri(c)

  def _restriction(self, r):
    prop      = r.property
    base_prop = prop.property if isinstance(prop, Inverse) else prop
    is_data   = isinstance(base_prop, DataPropertyClass)
    kind      = "Data" if is_data else "Object"
    pe        = self._property_expr(prop)
    t         = r.type

    if t == SOME:
      filler = self._data_range(r.value) if is_data else self._concept(r.value)
      return "%sSomeValuesFrom(%s %s)" % (kind, pe, filler)
    if t == ONLY:
      filler = self._data_range(r.value) if is_data else self._concept(r.value)
      return "%sAllValuesFrom(%s %s)" % (kind, pe, filler)
    if t == VALUE:
      filler = self._literal(r.value) if is_data else self._iri(r.value)
      return "%sHasValue(%s %s)" % (kind, pe, filler)
    if t == HAS_SELF:
      return "ObjectHasSelf(%s)" % pe

    # Cardinality restrictions (MIN / MAX / EXACTLY).
    keyword   = _CARD_KEYWORD[t]
    value     = getattr(r, "value", None)
    qualified = not ((value is None) or (value is Thing))
    if qualified:
      filler = self._data_range(value) if is_data else self._concept(value)
      return "%s%s(%d %s %s)" % (kind, keyword, r.cardinality, pe, filler)
    return "%s%s(%d %s)" % (kind, keyword, r.cardinality, pe)

  # ---- axioms ------------------------------------------------------------

  def _emit(self, axiom): self.lines.append(axiom)

  def _characteristics(self, prop):
    if isinstance(prop, DataPropertyClass):
      if issubclass(prop, FunctionalProperty): self._emit("FunctionalDataProperty(%s)" % self._iri(prop))
      return
    iri = self._iri(prop)
    if issubclass(prop, FunctionalProperty):        self._emit("FunctionalObjectProperty(%s)"        % iri)
    if issubclass(prop, InverseFunctionalProperty): self._emit("InverseFunctionalObjectProperty(%s)" % iri)
    if issubclass(prop, TransitiveProperty):        self._emit("TransitiveObjectProperty(%s)"        % iri)
    if issubclass(prop, SymmetricProperty):         self._emit("SymmetricObjectProperty(%s)"         % iri)
    if issubclass(prop, AsymmetricProperty):        self._emit("AsymmetricObjectProperty(%s)"        % iri)
    if issubclass(prop, ReflexiveProperty):         self._emit("ReflexiveObjectProperty(%s)"         % iri)
    if issubclass(prop, IrreflexiveProperty):       self._emit("IrreflexiveObjectProperty(%s)"       % iri)

  def _property(self, prop, is_data):
    kind = "Data" if is_data else "Object"
    self._emit("Declaration(%sProperty(%s))" % (kind, self._iri(prop)))
    for sup in prop.is_a:
      if isinstance(sup, PropertyChain):
        if not is_data:
          self._emit("SubObjectPropertyOf(ObjectPropertyChain(%s) %s)"
                     % (" ".join(self._property_expr(p) for p in sup.properties), self._iri(prop)))
      elif isinstance(sup, (ObjectPropertyClass, DataPropertyClass)) and (sup not in (ObjectProperty, DataProperty)) and (not _is_builtin_iri(sup.iri)):
        self._emit("Sub%sPropertyOf(%s %s)" % (kind, self._iri(prop), self._iri(sup)))
    self._characteristics(prop)
    for dom in prop.domain:
      self._emit("%sPropertyDomain(%s %s)" % (kind, self._iri(prop), self._concept(dom)))
    for rng in prop.range:
      filler = self._data_range(rng) if is_data else self._concept(rng)
      self._emit("%sPropertyRange(%s %s)" % (kind, self._iri(prop), filler))
    if not is_data:
      inv = prop.inverse_property
      if inv and (prop.storid < inv.storid):
        self._emit("InverseObjectProperties(%s %s)" % (self._iri(prop), self._iri(inv)))

  def export(self):
    w = self.world

    # Classes
    for klass in w.classes():
      if _is_builtin_iri(klass.iri): continue
      self._emit("Declaration(Class(%s))" % self._iri(klass))
      for sup in klass.is_a:
        if sup is Thing: continue
        if isinstance(sup, ThingClass) and _is_builtin_iri(sup.iri): continue
        self._emit("SubClassOf(%s %s)" % (self._iri(klass), self._concept(sup)))
      for eq in klass.equivalent_to:
        if isinstance(eq, ThingClass):
          if klass.storid < eq.storid:                          # emit each named pair once
            self._emit("EquivalentClasses(%s %s)" % (self._iri(klass), self._iri(eq)))
        else:
          self._emit("EquivalentClasses(%s %s)" % (self._iri(klass), self._concept(eq)))

    # Disjoint classes
    for d in w.disjoint_classes():
      rendered = [self._concept(e) for e in d.entities]
      if len(rendered) >= 2:
        self._emit("DisjointClasses(%s)" % " ".join(rendered))

    # Properties
    for prop in w.object_properties():
      if _is_builtin_iri(prop.iri): continue
      self._property(prop, is_data = False)
    for prop in w.data_properties():
      if _is_builtin_iri(prop.iri): continue
      self._property(prop, is_data = True)

    # Individuals
    for ind in w.individuals():
      if _is_builtin_iri(ind.iri): continue
      self._emit("Declaration(NamedIndividual(%s))" % self._iri(ind))
      for klass in ind.is_a:
        if klass is Thing: continue
        if isinstance(klass, ThingClass) and _is_builtin_iri(klass.iri): continue
        self._emit("ClassAssertion(%s %s)" % (self._concept(klass), self._iri(ind)))
      for prop in ind.get_properties():
        if not isinstance(prop, (ObjectPropertyClass, DataPropertyClass)): continue  # skip annotations
        is_data = isinstance(prop, DataPropertyClass)
        for value in prop[ind]:
          if is_data:
            self._emit("DataPropertyAssertion(%s %s %s)" % (self._iri(prop), self._iri(ind), self._literal(value)))
          else:
            self._emit("ObjectPropertyAssertion(%s %s %s)" % (self._iri(prop), self._iri(ind), self._iri(value)))

    # Same / different individuals
    for d in w.different_individuals():
      members = [self._iri(e) for e in d.entities]
      if len(members) >= 2:
        self._emit("DifferentIndividuals(%s)" % " ".join(members))

    return self.lines


def render_world_functional_syntax(world, onto_iri = "http://owlready3/merged"):
  """Return the World serialized as an OWL 2 Functional-Style Syntax string."""
  # Clear the active namespace stack during export: anonymous constructs such as
  # AllDisjoint otherwise bind to the enclosing `with onto:` ontology (rather than
  # the one that actually holds their RDF list), which breaks list lookups when
  # sync_reasoner() is called inside a `with` block.
  token = CURRENT_NAMESPACES.set([])
  try:
    axioms = _FunctionalSyntaxExporter(world).export()
  finally:
    CURRENT_NAMESPACES.reset(token)
  body = "\n".join(axioms)
  return "Ontology(<%s>\n%s\n)\n" % (onto_iri, body)


def save_world_functional_syntax(world, file, onto_iri = "http://owlready3/merged"):
  """Write the World to `file` (path or binary file object) as Functional Syntax."""
  text = render_world_functional_syntax(world, onto_iri)
  if isinstance(file, str):
    with open(file, "w", encoding = "utf-8") as f: f.write(text)
  else:
    file.write(text.encode("utf-8"))
  return text
