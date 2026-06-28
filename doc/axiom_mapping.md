# OWL 2 Axioms: owlapy ↔ owlready3 mapping

How to query each OWL 2 axiom type in **owlready3**, alongside the equivalent
[owlapy](https://github.com/dice-group/owlapy) axiom class.

The two libraries take opposite approaches:

- **owlapy** mirrors the Java OWL API: every axiom is a first-class object
  (`OWLSubClassOfAxiom`, `OWLClassAssertionAxiom`, …) that you build and add to an
  ontology, and read back via accessors such as `onto.get_tbox_axioms()`.
- **owlready3** has *no axiom objects*. The same information lives in the Python
  object graph — classes are Python classes, property values are attributes — so
  you "query an axiom" by reading the relevant attribute/method of a class,
  property, or individual (or by querying the triplestore directly).

> Asserted vs. inferred: plain accessors (`is_a`, `prop[ind]`, `ind.prop`) return
> **asserted** facts. Prefix with **`INDIRECT_`** (e.g. `ind.INDIRECT_is_a`,
> `ind.INDIRECT_hasChild`) to include reasoner-inferred facts after
> `sync_reasoner_rustdl()`. For anything not exposed as an attribute, fall back to
> `onto.world.sparql(...)` or `list(onto.get_triples())`, which always works.

All owlready3 accessors below are verified against the owlready3 in this repo.

---

## Declaration

| owlapy axiom | owlready3 query |
|---|---|
| `OWLDeclarationAxiom` | `onto.classes()`, `onto.object_properties()`, `onto.data_properties()`, `onto.annotation_properties()`, `onto.individuals()`; or `world[iri]` / `onto.Name` |

## Class axioms (TBox)

| owlapy axiom | Asserts | owlready3 query |
|---|---|---|
| `OWLSubClassOfAxiom` | `C ⊑ D` | `cls.is_a` (named supers + restrictions); `cls.subclasses()` (direct subs); `cls.ancestors()` / `cls.descendants()` |
| `OWLEquivalentClassesAxiom` | `C ≡ D` | `cls.equivalent_to` (+ `cls.INDIRECT_equivalent_to`) |
| `OWLDisjointClassesAxiom` | pairwise disjoint | `onto.disjoint_classes()` → groups; `cls.disjoints()` |
| `OWLDisjointUnionAxiom` | covering disjoint partition | `cls.disjoint_unions` |

## Object-property axioms (RBox)

| owlapy axiom | Asserts | owlready3 query |
|---|---|---|
| `OWLSubObjectPropertyOfAxiom` | `P ⊑ Q` | `prop.is_a` (super-props); `prop.descendants()` / `prop.ancestors()` |
| `OWLSubPropertyChainAxiom` | `P₁∘…∘Pₙ ⊑ Q` | `prop.get_property_chain()` → `PropertyChain.properties` |
| `OWLEquivalentObjectPropertiesAxiom` | `P ≡ Q` | `prop.equivalent_to` |
| `OWLDisjointObjectPropertiesAxiom` | disjoint | `onto.disjoint_properties()`; `prop.disjoints()` |
| `OWLInverseObjectPropertiesAxiom` | `P ≡ Q⁻` | `prop.inverse_property` (alias `prop.inverse`) |
| `OWLObjectPropertyDomainAxiom` | `∃P.⊤ ⊑ C` | `prop.domain` |
| `OWLObjectPropertyRangeAxiom` | `⊤ ⊑ ∀P.C` | `prop.range` |
| `OWLFunctionalObjectPropertyAxiom` | ≤1 value/subject | `FunctionalProperty in prop.is_a` (or `issubclass(prop, FunctionalProperty)`) |
| `OWLInverseFunctionalObjectPropertyAxiom` | ≤1 subject/value | `InverseFunctionalProperty in prop.is_a` |
| `OWLReflexiveObjectPropertyAxiom` | `x P x` ∀x | `ReflexiveProperty in prop.is_a` |
| `OWLIrreflexiveObjectPropertyAxiom` | no `x P x` | `IrreflexiveProperty in prop.is_a` |
| `OWLSymmetricObjectPropertyAxiom` | `x P y ⇒ y P x` | `SymmetricProperty in prop.is_a` |
| `OWLAsymmetricObjectPropertyAxiom` | `x P y ⇒ ¬ y P x` | `AsymmetricProperty in prop.is_a` |
| `OWLTransitiveObjectPropertyAxiom` | `x P y ∧ y P z ⇒ x P z` | `TransitiveProperty in prop.is_a` |

## Data-property axioms (RBox)

| owlapy axiom | Asserts | owlready3 query |
|---|---|---|
| `OWLSubDataPropertyOfAxiom` | `R ⊑ S` | `prop.is_a` |
| `OWLEquivalentDataPropertiesAxiom` | `R ≡ S` | `prop.equivalent_to` |
| `OWLDisjointDataPropertiesAxiom` | disjoint | `onto.disjoint_properties()`; `prop.disjoints()` |
| `OWLDataPropertyDomainAxiom` | `x R v ⇒ x ∈ C` | `prop.domain` |
| `OWLDataPropertyRangeAxiom` | `x R v ⇒ v ∈ dr` | `prop.range` (Python types, e.g. `str`, `int`) |
| `OWLFunctionalDataPropertyAxiom` | ≤1 value/subject | `FunctionalProperty in prop.is_a` |

## Datatype & keys

| owlapy axiom | owlready3 query |
|---|---|
| `OWLDatatypeDefinitionAxiom` | ⚠️ **Limited** — custom datatypes via `ConstrainedDatatype`/declared datatypes; no dedicated axiom accessor |
| `OWLHasKeyAxiom` | ❌ **Not supported** (no `has_key` in this build) |

## Assertion / individual axioms (ABox)

| owlapy axiom | Asserts | owlready3 query |
|---|---|---|
| `OWLClassAssertionAxiom` | `a ∈ C` | `ind.is_a` (asserted), `ind.INDIRECT_is_a` (incl. inferred); `cls.instances()` |
| `OWLObjectPropertyAssertionAxiom` | `a P b` | `ind.propName` or `prop[ind]`; `ind.get_properties()`; `ind.INDIRECT_propName` for inferred |
| `OWLDataPropertyAssertionAxiom` | `a R "v"` | `ind.propName` or `prop[ind]` |
| `OWLNegativeObjectPropertyAssertionAxiom` | `¬ a P b` | ❌ **Not supported** |
| `OWLNegativeDataPropertyAssertionAxiom` | `¬ a R "v"` | ❌ **Not supported** |
| `OWLSameIndividualAxiom` | `owl:sameAs` | `ind.equivalent_to` |
| `OWLDifferentIndividualsAxiom` | pairwise distinct | `onto.different_individuals()` → groups; `ind.differents()` |

## Annotation axioms (non-logical)

| owlapy axiom | owlready3 query |
|---|---|
| `OWLAnnotationAssertionAxiom` | `entity.label`, `entity.comment`, or `entity.<annotProp>` (any entity/IRI) |
| `OWLAnnotationPropertyDomainAxiom` | `annot_prop.domain` |
| `OWLAnnotationPropertyRangeAxiom` | `annot_prop.range` |
| `OWLSubAnnotationPropertyOfAxiom` | `annot_prop.is_a` |

---

## Gaps in owlready3

These OWL 2 axioms have **no direct owlready3 accessor** in this build:

- `OWLHasKeyAxiom` — keys are not modelled.
- `OWLNegativeObjectPropertyAssertionAxiom` / `OWLNegativeDataPropertyAssertionAxiom` — negative assertions are not modelled.
- `OWLDatatypeDefinitionAxiom` — only partial/indirect support.

For these, query the underlying triples (`onto.world.sparql(...)` /
`onto.get_triples()`) if the source RDF contains them.

## Retrieving *inferred* axioms

After reasoning, the inferred counterparts can be read directly from rustdl
(bypassing the object graph):

```python
import rustdl
rustdl.materialize_inferred_class_assertions("onto.ofn")        # (class, individual)
rustdl.materialize_inferred_property_assertions("onto.ofn")     # (subj, prop, obj)
rustdl.materialize_inferred_data_property_assertions("onto.ofn")# (subj, prop, value, datatype, lang)
rustdl.materialize_inferred_subclass_axioms("onto.ofn")         # (sub, sup)
```

Each returns *entailed* facts (asserted **+** inferred); for *only* inferred,
subtract the asserted set. The `.ofn` is produced with
`owlready3.fs_render.save_world_functional_syntax(world, "onto.ofn")`.

In the object-graph idiom, the equivalent is `sync_reasoner_rustdl(onto)` followed
by the `INDIRECT_*` accessors above (e.g. `ind.INDIRECT_is_a`), which apply the
inferences to the live Python objects.

To get just the **class assertions that the last reasoning run inferred** (the new
`rdf:type` triples, excluding the asserted ones), use `get_inferred_class_assertions()`
(module function, also a method on `World`/`Ontology`):

```python
from owlready3 import get_inferred_class_assertions, sync_reasoner_rustdl

sync_reasoner_rustdl(onto)
onto.get_inferred_class_assertions()   # -> [(individual, class), ...] most-specific, inferred only
```

It returns `(individual, class)` entity pairs, is reset on each reasoning run, and is
empty before the first run (or if nothing new was inferred).

Likewise, `get_inferred_property_assertions()` returns the inferred object/data
property assertions as `(subject, property, value)` triples (value is an individual
for object properties, a literal for data properties). It requires the materialization
flags and only covers property-box entailments (sub-property, inverse, symmetric, …):

```python
sync_reasoner_rustdl(onto, infer_property_values = True, infer_data_property_values = True)
onto.get_inferred_property_assertions()  # -> [(subj, prop, value), ...] inferred only
```

## Explaining entailments (justifications & repairs)

owlapy exposes axiom justifications (`SyncReasoner.create_axiom_justifications`).
owlready3 offers the equivalent via `explain()` / `why_inconsistent()` / `repairs()`
(module functions, also methods on `World` and `Ontology`), backed by rustdl:

```python
from owlready3 import explain, Nothing

explain(Dog, Animal)        # why Dog ⊑ Animal  -> ['<…#Dog> SubClassOf <…#Animal>']
onto.explain(Carnivore)     # why Carnivore is unsatisfiable (Carnivore ⊑ Nothing)
                            #   -> the minimal set of axioms causing it
onto.explain(C, D, all=True)# every minimal justification (list of lists)
onto.repairs(Carnivore)     # axiom sets to remove to break the entailment
onto.why_inconsistent()     # justification for an inconsistent ontology ([] if consistent)
```

`sub`/`sup` are named classes; results are Manchester axiom strings. An empty
result means the entailment does not hold. This requires no reasoning step
beforehand (the query reasons on demand) and no JVM.
