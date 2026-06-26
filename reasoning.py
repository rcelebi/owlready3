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

# Lightweight build: ontology reasoning is delegated to the native Rust
# OWL 2 DL (SROIQ) reasoner `rustdl` (https://github.com/MaastrichtU-IDS/rustdl),
# replacing the previous Java-based HermiT / Pellet integrations. Install it with:
#
#     pip install rustdl

import tempfile, warnings

import owlready3
from owlready3.base            import *
from owlready3.base            import to_literal, from_literal, locstr
from owlready3.prop            import *
from owlready3.namespace       import *
from owlready3.class_construct import *
from owlready3.individual      import *


_TYPE_2_IS_A = {
  "class"                 : rdfs_subclassof,
  "property"              : rdfs_subpropertyof,
  "individual"            : rdf_type,
}
_TYPE_2_EQUIVALENT_TO = {
  "class"                 : owl_equivalentclass,
  "property"              : owl_equivalentproperty,
  "individual"            : owl_equivalentindividual,
}

_INFERRENCES_ONTOLOGY = "http://inferrences/"

_TYPES = { FunctionalProperty, InverseFunctionalProperty, TransitiveProperty, SymmetricProperty, AsymmetricProperty, ReflexiveProperty, IrreflexiveProperty }

# Default per-subsumption-pair tableau budget passed to rustdl.classify().
# 0 means unbounded (complete, but potentially slow on pathological inputs).
RUSTDL_PER_PAIR_TIMEOUT_MS = 1000


def _keep_most_specific(s, consider_equivalence = True):
  r = set()
  if consider_equivalence:
    for i in s:
      if isinstance(i, Construct): r.add(i)
      else:
        for j in s:
          if (i is j) or isinstance(j, Construct): continue
          if issubclass(j, i) and ((i.storid < j.storid) or (issubclass_python(j, i))): break
        else:
          r.add(i)
  else:
    for i in s:
      if isinstance(i, Construct): r.add(i)
      else:
        for j in s:
          if (i is j) or isinstance(j, Construct): continue
          if issubclass_python(j, i): break
        else:
          r.add(i)
  return r


def _load_rustdl():
  try:
    import rustdl
  except ImportError:
    raise OwlReadyError(
      "* Owlready3 * The 'rustdl' reasoner is required by sync_reasoner() but is not installed.\n"
      "    Install it with:  pip install owlready3[reasoning]   (or: pip install rustdl)")
  return rustdl


def _direct_supers(closure):
  """Transitive reduction of a strict-subsumption closure.

  `closure` maps a class IRI to the set of all its strict superclass IRIs.
  Returns a mapping class IRI -> set of *direct* superclass IRIs (i.e. with
  no intermediate class in between)."""
  direct = {}
  for node, supers in closure.items():
    direct[node] = set(
      sup for sup in supers
      if not any((m != sup) and (sup in closure.get(m, ())) for m in supers))
  return direct


def _most_specific_types(types_set, sub_closure):
  """Among the entailed types of an individual, keep only the most specific
  ones (drop any class that is a strict superclass of another entailed type)."""
  return set(
    c for c in types_set
    if not any((c2 != c) and (c in sub_closure.get(c2, ())) for c2 in types_set))


def sync_reasoner_rustdl(x = None, infer_property_values = False, infer_data_property_values = False,
                         debug = 1, keep_tmp_file = False,
                         per_pair_timeout_ms = RUSTDL_PER_PAIR_TIMEOUT_MS, saturation_only = False):
  """Classify and realize the ontology with the native rustdl reasoner.

  Inferred class subsumptions, class equivalences, unsatisfiable classes
  (made equivalent to owl:Nothing) and individual type assertions are applied
  back onto the quadstore and the loaded Python entities, exactly like the
  previous HermiT / Pellet integrations.

  `per_pair_timeout_ms` bounds each subsumption test (0 = unbounded/complete).
  `saturation_only` restricts rustdl to the fast EL-closure under-approximation.

  When `infer_property_values` / `infer_data_property_values` are set, rustdl's
  inferred object / data property assertions are materialized back onto the
  quadstore and the loaded Python entities. rustdl materializes assertions
  entailed by the property box (sub-property, inverse, symmetric, …); it does
  not derive values from hasValue restrictions, owl:sameAs propagation or SWRL
  rules, so those particular entailments will not appear."""
  rustdl = _load_rustdl()

  if   isinstance(x, World):    world = x
  elif isinstance(x, Ontology): world = x.world
  elif isinstance(x, list):     world = x[0].world
  else:                         world = owlready3.default_world

  inferred_obj_relations  = []
  inferred_data_relations = []

  locked = world.graph.has_write_lock()
  if locked: world.graph.release_write_lock() # Not needed during reasoning

  try:
    if   isinstance(x, Ontology):  ontology = x
    elif CURRENT_NAMESPACES.get(): ontology = CURRENT_NAMESPACES.get()[-1].ontology
    else:                          ontology = world.get_ontology(_INFERRENCES_ONTOLOGY)

    # Export to OWL Functional Syntax (.ofn) rather than RDF/XML: rustdl's
    # RDF/XML reader does not reconstruct some nested anonymous class
    # expressions (e.g. ObjectComplementOf around ObjectSomeValuesFrom), while
    # its Functional-Syntax reader is complete. The whole world is exported
    # (it contains every loaded ontology); results are applied to the world.
    from owlready3.fs_render import save_world_functional_syntax
    tmp = tempfile.NamedTemporaryFile("wb", suffix = ".ofn", delete = False)
    tmp.close()
    save_world_functional_syntax(world, tmp.name)

    if debug:
      import time
      print("* Owlready3 * Running rustdl...", file = sys.stderr)
      print("    rustdl.classify(%r, per_pair_timeout_ms = %s, saturation_only = %s)"
            % (tmp.name, per_pair_timeout_ms, saturation_only), file = sys.stderr)
      t0 = time.time()

    try:
      if not rustdl.is_consistent(tmp.name):
        raise OwlReadyInconsistentOntologyError()

      classification = rustdl.classify(tmp.name, per_pair_timeout_ms = per_pair_timeout_ms, saturation_only = saturation_only)
      sub_axioms     = rustdl.materialize_inferred_subclass_axioms(tmp.name)
      type_axioms    = rustdl.materialize_inferred_class_assertions(tmp.name)
      obj_assertions  = rustdl.materialize_inferred_property_assertions(tmp.name)      if infer_property_values      else []
      data_assertions = rustdl.materialize_inferred_data_property_assertions(tmp.name) if infer_data_property_values else []
    except OwlReadyInconsistentOntologyError:
      raise
    except rustdl.ParseError as e:
      raise OwlReadyOntologyParsingError("* Owlready3 * rustdl could not parse the ontology:\n%s" % e)
    except Exception as e:
      raise OwlReadyError("* Owlready3 * rustdl reasoning error:\n%s" % e)

    if debug:
      print("* Owlready3 * rustdl took %s seconds" % (time.time() - t0), file = sys.stderr)
      if not getattr(classification, "complete", True):
        print("* Owlready3 * Warning: rustdl classification is incomplete (%s subsumption pair(s) timed out); "
              "some subsumptions may be missing. Increase per_pair_timeout_ms (0 = unbounded)."
              % getattr(classification, "timed_out_pairs", "?"), file = sys.stderr)
      if debug > 1:
        print("* Owlready3 * rustdl inferred %s subclass axiom(s), %s class assertion(s), %s unsatisfiable class(es)"
              % (len(sub_axioms), len(type_axioms), len(classification.unsatisfiable)), file = sys.stderr)

    # rustdl returns the full entailed subsumption closure; reduce it to direct
    # facts so the asserted triples / reparenting mirror the previous reasoners.
    sub_pairs    = set((sub, sup) for (sub, sup) in sub_axioms)
    equiv_pairs  = set((a, b) for (a, b) in sub_pairs if (b, a) in sub_pairs)   # mutual subsumption = equivalence
    strict_pairs = sub_pairs - equiv_pairs

    sub_closure = defaultdict(set)
    for sub, sup in strict_pairs: sub_closure[sub].add(sup)

    new_parents   = defaultdict(list)
    new_equivs    = defaultdict(list)
    entity_2_type = {}

    # Direct class subsumptions
    for sub, sups in _direct_supers(sub_closure).items():
      sub_storid = ontology._abbreviate(sub)
      entity_2_type[sub_storid] = "class"
      for sup in sups:
        new_parents[sub_storid].append(ontology._abbreviate(sup))

    # Equivalences between named classes
    for a, b in equiv_pairs:
      a_storid = ontology._abbreviate(a)
      entity_2_type[a_storid] = "class"
      new_equivs[a_storid].append(ontology._abbreviate(b))

    # Unsatisfiable classes are equivalent to owl:Nothing
    for iri in classification.unsatisfiable:
      storid = ontology._abbreviate(iri)
      entity_2_type[storid] = "class"
      if owl_nothing not in new_equivs[storid]:
        new_equivs[storid].append(owl_nothing)

    # Class assertions: keep the most specific entailed type(s) per individual
    individual_types = defaultdict(set)
    for cls, ind in type_axioms: individual_types[ind].add(cls)
    for ind, types_set in individual_types.items():
      ind_storid = ontology._abbreviate(ind)
      entity_2_type[ind_storid] = "individual"
      for cls in _most_specific_types(types_set, sub_closure):
        new_parents[ind_storid].append(ontology._abbreviate(cls))

    # Inferred object property assertions (keep only the genuinely new ones).
    for s_iri, p_iri, o_iri in obj_assertions:
      s_storid = ontology._abbreviate(s_iri)
      p_storid = ontology._abbreviate(p_iri)
      o_storid = ontology._abbreviate(o_iri)
      if world._has_obj_triple_spo(s_storid, p_storid, o_storid): continue
      prop = world._get_by_storid(p_storid)
      if prop is None: continue
      inferred_obj_relations.append((s_storid, prop, o_storid))

    # Inferred data property assertions. rustdl yields 5-tuples
    # (subject, property, lexical_value, datatype_iri, lang).
    for s_iri, p_iri, value_str, datatype_iri, lang in data_assertions:
      s_storid = ontology._abbreviate(s_iri)
      p_storid = ontology._abbreviate(p_iri)
      prop = world._get_by_storid(p_storid)
      if prop is None: continue
      if lang: python_value = locstr(value_str, lang)
      else:    python_value = from_literal(value_str, ontology._abbreviate(datatype_iri))
      value, datatype = to_literal(python_value)
      if world._has_data_triple_spod(s_storid, p_storid, value, datatype): continue
      inferred_data_relations.append((s_storid, prop, value, datatype))

    if not keep_tmp_file: os.unlink(tmp.name)

  finally:
    if locked: world.graph.acquire_write_lock() # re-lock when applying results

  _apply_reasoning_results(world, ontology, debug, new_parents, new_equivs, entity_2_type)

  if inferred_obj_relations:  _apply_inferred_obj_relations (world, ontology, debug, inferred_obj_relations)
  if inferred_data_relations: _apply_inferred_data_relations(world, ontology, debug, inferred_data_relations)

  if debug: print("* Owlready * (NB: only changes on entities loaded in Python are shown, other changes are done but not listed)", file = sys.stderr)


# Default reasoner entry point.
sync_reasoner = sync_reasoner_rustdl


def sync_reasoner_hermit(*args, **kargs):
  """Deprecated: HermiT was removed from the lightweight build and replaced by
  rustdl. Delegates to sync_reasoner_rustdl()."""
  warnings.warn("* Owlready3 * sync_reasoner_hermit() is deprecated: HermiT was replaced by rustdl. "
                "Delegating to sync_reasoner_rustdl().", DeprecationWarning, stacklevel = 2)
  return sync_reasoner_rustdl(*args, **kargs)


def sync_reasoner_pellet(*args, **kargs):
  """Deprecated: Pellet was removed from the lightweight build and replaced by
  rustdl. Delegates to sync_reasoner_rustdl()."""
  warnings.warn("* Owlready3 * sync_reasoner_pellet() is deprecated: Pellet was replaced by rustdl. "
                "Delegating to sync_reasoner_rustdl().", DeprecationWarning, stacklevel = 2)
  return sync_reasoner_rustdl(*args, **kargs)


def _apply_reasoning_results(world, ontology, debug, new_parents, new_equivs, entity_2_type):
  new_parents_loaded = defaultdict(list)
  new_equivs_loaded  = defaultdict(list)

  for child_storid, parent_storids in new_parents.items():
    for parent_storid in parent_storids:
      owl_relation = _TYPE_2_IS_A[entity_2_type[child_storid]]
      if not ontology.world._has_obj_triple_spo(child_storid, owl_relation, parent_storid):
        ontology._add_obj_triple_spo(child_storid, owl_relation, parent_storid)

    child = world._entities.get(child_storid)
    if not child is None:
      l = new_parents_loaded[child] = []
      for parent_storid in parent_storids:
        parent = world._get_by_storid(parent_storid)
        if parent is None:
          print("* Owlready3 * Warning: Cannot find new parent '%s'" % parent_storid, file = sys.stderr)
        else:
          l.append(parent)

  for concept1_storid, concept2_storids in new_equivs.items():
    for concept2_storid in concept2_storids:
      owl_relation = _TYPE_2_EQUIVALENT_TO[entity_2_type[concept1_storid]]
      if not ontology.world._has_obj_triple_spo(concept1_storid, owl_relation, concept2_storid):
        ontology._add_obj_triple_spo(concept1_storid, owl_relation, concept2_storid)

      if concept2_storid == owl_nothing:
        concept1 = world._entities.get(concept1_storid)
        if not concept1 is None: new_equivs_loaded[concept1].append(Nothing)
      else:
        concept1 = world._entities.get(concept1_storid)
        concept2 = world._entities.get(concept2_storid)
        if concept1 or concept2:
          concept1 = concept1 or world._get_by_storid(concept1_storid)
          concept2 = concept2 or world._get_by_storid(concept2_storid)
          if not concept1 is concept2: new_equivs_loaded[concept1].append(concept2)


  with LOADING: # Because triples were asserted above => only modify Python objects WITHOUT creating new triples!
    for concept1, concepts2 in new_equivs_loaded.items():
      for concept2 in concepts2:
        if debug: print("* Owlready * Equivalenting:", concept1, concept2, file = sys.stderr)
        if not concept2 in concept1.equivalent_to: concept1.equivalent_to._append(concept2)

    for child, parents in new_parents_loaded.items():
      old = set(parent for parent in child.is_a if not isinstance(parent, Construct))
      new = set(parents)

      #new.update([parent_eq for parent in new for parent_eq in parent.equivalent_to.indirect() if not isinstance(parent, Construct)])

      new.update(old & _TYPES) # Types are not shown by the reasoner
      if old == new: continue
      new = _keep_most_specific(new, consider_equivalence = False)
      if old == new: continue

      if debug: print("* Owlready * Reparenting %s:" % child, old, "=>", new, file = sys.stderr)
      new_is_a = list(child.is_a)
      for removed in old - new: new_is_a.remove(removed)
      for added   in new - old: new_is_a.append(added)

      child.is_a.reinit(new_is_a)

      for child_eq in child.equivalent_to.indirect():
        if isinstance(child_eq, ThingClass):
          if debug: print("* Owlready * Reparenting %s (since equivalent):" % child_eq, old, "=>", new, file = sys.stderr)
          new_is_a = list(child_eq.is_a)
          for removed in old - new:
            if removed in new_is_a: new_is_a.remove(removed)
          for added   in new - old:
            if not added in new_is_a: new_is_a.append(added)
          child_eq.is_a.reinit(new_is_a)


def _apply_inferred_obj_relations(world, ontology, debug, relations):
  for a_storid, prop, b_storid in relations:
    ontology._add_obj_triple_spo(a_storid, prop.storid, b_storid)

    a = world._entities.get(a_storid)
    if not a is None:
      if debug:
        b = world._entities.get(b_storid)
        if not b is None: print("* Owlready * Adding relation %s %s %s" % (a, prop.name, b))
      if prop._python_name in a.__dict__:
        delattr(a, prop._python_name)

    if prop._inverse_property:
      b = world._entities.get(b_storid)
      if not b is None:
        if prop._inverse_property._python_name in b.__dict__:
          delattr(b, prop._inverse_property._python_name)


def _apply_inferred_data_relations(world, ontology, debug, relations):
  for a_storid, prop, value, datatype in relations:
    ontology._add_data_triple_spod(a_storid, prop.storid, value, datatype)

    a = world._entities.get(a_storid)
    if not a is None:
      if debug:
        print("* Owlready * Adding relation %s %s %s" % (a, prop.name, value))
      if prop._python_name in a.__dict__:
        delattr(a, prop._python_name)
