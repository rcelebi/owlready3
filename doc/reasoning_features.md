# Reasoning features (rustdl)

owlready3 reasons with the native **rustdl** OWL 2 DL reasoner — no JVM, no Java
reasoner JARs. Beyond classification and realization, this build adds three
capabilities, each a thin Python wrapper over functionality rustdl already
computes:

1. [Property-value materialization](#1-property-value-materialization)
2. [Explanations — justifications & repairs](#2-explanations--justifications--repairs)
3. [Retrieving inferred assertions after reasoning](#3-retrieving-inferred-assertions-after-reasoning)

All examples assume:

```python
import owlready3 as owl
from owlready3 import sync_reasoner_rustdl   # also exported as sync_reasoner
```

> **What rustdl infers.** rustdl materializes class subsumptions, class
> assertions (realization), and **property-box** property assertions
> (sub-property, inverse, symmetric, …). It does **not** derive values from
> `hasValue` restrictions, propagate across `owl:sameAs`, or fire **SWRL** rules —
> those entailments will not appear. For full SROIQ coverage of those constructs,
> a HermiT/Pellet-class reasoner is needed.

---

## 1. Property-value materialization

By default `sync_reasoner_rustdl()` applies inferred subsumptions and class
assertions. Pass `infer_property_values` / `infer_data_property_values` to also
materialize inferred **object / data property** assertions onto the quadstore and
the loaded Python objects:

```python
with onto:
    sync_reasoner_rustdl(onto,
                         infer_property_values      = True,   # object properties
                         infer_data_property_values = True)   # data properties

mary.hasParent          # now includes values inferred via sub-property / inverse
```

This covers entailments from the property box — e.g. with `hasFather ⊑ hasParent`
and `hasParent ≡ hasChild⁻`, asserting `mary hasFather john` infers
`mary hasParent john` and `john hasChild mary`.

---

## 2. Explanations — justifications & repairs

Answer *"why is this entailed?"* and *"why is my ontology inconsistent?"* — a
long-standing gap in the owlready line. Available as module functions and as
methods on `World` / `Ontology`.

```python
from owlready3 import explain, why_inconsistent, repairs, Nothing

explain(Dog, Animal)         # why Dog ⊑ Animal  -> ['<…#Dog> SubClassOf <…#Animal>']
onto.explain(Carnivore)      # why Carnivore is unsatisfiable (Carnivore ⊑ Nothing)
                             #   -> minimal set of axioms causing it
onto.explain(C, D, all=True) # every minimal justification (list of lists)
onto.repairs(Carnivore)      # axiom sets to remove to break the entailment
onto.why_inconsistent()      # justification for an inconsistent ontology ([] if consistent)
```

- `sub` / `sup` are **named classes**; `sup=None` (or `Nothing`) asks for
  unsatisfiability.
- Results are **Manchester axiom strings**. An empty result means *not entailed*.
- No prior `sync_reasoner` call is required — the query reasons on demand.

Example — explaining an unsatisfiable class:

```python
with onto:
    class Animal(owl.Thing): pass
    class Plant(owl.Thing): pass
    class Dog(Animal): pass
    owl.AllDisjoint([Animal, Plant])
    class Carnivore(Dog): pass
    Carnivore.is_a.append(Plant)          # contradiction

onto.explain(Carnivore)
# ['<…#Carnivore> SubClassOf <…#Dog>',
#  '<…#Dog> SubClassOf <…#Animal>',
#  '<…#Animal> DisjointWith <…#Plant>',
#  '<…#Carnivore> SubClassOf <…#Plant>']

onto.repairs(Carnivore)   # remove ANY one of these to fix it
# [['<…#Dog> SubClassOf <…#Animal>'], ['<…#Carnivore> SubClassOf <…#Dog>'],
#  ['<…#Carnivore> SubClassOf <…#Plant>'], ['<…#Animal> DisjointWith <…#Plant>']]
```

---

## 3. Retrieving inferred assertions after reasoning

Once `sync_reasoner_rustdl()` applies its inferences to the live objects, the
asserted-vs-inferred distinction is otherwise lost (a triple diff would need a
pre-reasoning snapshot). These accessors return *only* what the **last run
inferred** — recorded during reasoning. Module functions, also methods on
`World` / `Ontology`.

### Inferred class assertions

```python
from owlready3 import get_inferred_class_assertions

with onto:
    sync_reasoner_rustdl(onto)
onto.get_inferred_class_assertions()
# -> [(a, Grandparent), (b, Parent)]   (individual, class) — most-specific, inferred only
```

Returns `(individual, class)` entity pairs (most-specific types), excluding
asserted types. Reset on every run; empty before the first run or if nothing new
was inferred.

### Inferred property assertions

```python
from owlready3 import get_inferred_property_assertions

with onto:
    sync_reasoner_rustdl(onto, infer_property_values = True,
                         infer_data_property_values = True)
onto.get_inferred_property_assertions()
# -> [(john, hasChild, mary), (mary, hasParent, john), (john, dsuper, 42)]
```

Returns `(subject, property, value)` triples — `value` is an individual for object
properties, a literal for data properties. **Requires the materialization flags**
(see §1); empty otherwise. Reset on every run.

---

## Raw rustdl access

All of the above wrap functions on the `rustdl` module, which you can call
directly on an OWL Functional Syntax (`.ofn`) file. Export the world with
`owlready3.fs_render.save_world_functional_syntax(world, "onto.ofn")`, then:

| `rustdl` function | Returns |
|---|---|
| `materialize_inferred_class_assertions(path)` | `(class, individual)` pairs |
| `materialize_inferred_property_assertions(path)` | `(subject, property, object)` |
| `materialize_inferred_data_property_assertions(path)` | `(subject, property, value, datatype, lang)` |
| `materialize_inferred_subclass_axioms(path)` | `(sub, sup)` |
| `justify(path, query)` / `justify_all(path, query, max=…)` | minimal justification(s) |
| `repair(path, query, max=…)` | repair axiom sets |
| `diagnose(path)` | `(consistent, roots, [(derived, [roots])])` |

`query` is a CLI-style token list: `["subclass", sub, sup]`, `["unsat", c]`, or
`["inconsistent"]`. The `materialize_*` functions return *entailed* facts (asserted
**+** inferred); subtract the asserted set for *only* inferred, or use the
owlready3 accessors in §3 which already do this.
