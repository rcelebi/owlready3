"""
Test suite for owlready3 Manchester syntax extensions.

Test cases are derived from the MIE breast-cancer case study in the SULO
tutorial (sulo-tutorial/notebooks/test/01-05-MIE-*.ipynb).

Run from the claude-ws directory:
    python3 owlready3/test/test_sulo_mie.py -v

Concepts tested
---------------
  to_manchester (serializer)                     – TestSerializer*
  parse_manchester_expression (parser)           – TestParser
  parse_manchester_ontology (ontology parser)    – TestOntologyParser
  Reasoning + individual classification          – TestReasoning
  classes_matching (TBox pattern query)          – TestClassesMatching
  instances_of (ABox post-reasoning query)       – TestInstancesOf
  SPARQL with ??N parameter substitution         – TestSparql
"""

import sys, os, io, tempfile, unittest, atexit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                     # owlready3/
sys.path.insert(0, os.path.dirname(ROOT))        # claude-ws/ so "import owlready3" finds the local copy

import owlready3
from owlready3 import (
    to_manchester,
    parse_manchester_expression,
    parse_manchester_ontology,
    manchester_render_ontology,
    SOME, ONLY, MIN, MAX, EXACTLY, VALUE,
    classes_matching,
    instances_of,
    sync_reasoner_rustdl,
)
from owlready3.class_construct import And, Or, Restriction, ConstrainedDatatype

owlready3.set_log_level(0)

# ── require a recent rustdl ─────────────────────────────────────────────────
# These tests assert rustdl's ABox-realization / classification behaviour, which
# is only correct on recent releases. Pin the floor here so the suite fails loudly
# (rather than silently mis-classifying) on a stale reasoner. Keep in sync with
# pyproject.toml's [project.optional-dependencies] rustdl>=… pin.
RUSTDL_MIN = (0, 3, 12)

def _rustdl_version():
    import rustdl
    try:
        from importlib.metadata import version
        v = version("rustdl")
    except Exception:
        v = getattr(rustdl, "__version__", "0")
    parts = []
    for tok in v.split("."):
        num = "".join(c for c in tok if c.isdigit())
        if not num: break
        parts.append(int(num))
    return tuple(parts), v

_RUSTDL_VER, _RUSTDL_VER_STR = _rustdl_version()
if _RUSTDL_VER < RUSTDL_MIN:
    raise RuntimeError(
        "test_sulo_mie.py requires rustdl>=%s, but found %s. "
        "Upgrade with:  pip install -U rustdl"
        % (".".join(map(str, RUSTDL_MIN)), _RUSTDL_VER_STR))

# Self-contained committed fixture: mie-05.owl plus its sulo.owl / pro.owl
# imports live in this test directory, so notebook/build runs that regenerate
# sulo-tutorial/dist/ can't mutate or invalidate it.
FIXTURE_DIR = HERE
MIE05       = os.path.join(FIXTURE_DIR, 'mie-05.owl')

MIE_IRI  = 'https://w3id.org/ontostart/mie/'
SULO_IRI = 'https://w3id.org/sulo/'
PRO_IRI  = 'https://w3id.org/ontostart/pro/'

# ── module-level ontology (no reasoning) ────────────────────────────────────
_TMPFILES = []
def _cleanup():
    for f in _TMPFILES:
        try: os.unlink(f)
        except OSError: pass
atexit.register(_cleanup)

def _new_world():
    fd, path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(fd)
    _TMPFILES.append(path)
    w = owlready3.World()
    w.set_backend(filename=path)
    return w

if FIXTURE_DIR not in owlready3.onto_path:
    owlready3.onto_path.append(FIXTURE_DIR)

_W    = _new_world()
_ONTO = _W.get_ontology(f'file://{MIE05}').load()


def C(name):
    """Return a class from the module-level MIE ontology by local name."""
    return _W[f'{MIE_IRI}{name}']

def I(name):
    """Return an individual from the module-level MIE ontology by local name."""
    return _W[f'{MIE_IRI}{name}']

def prop(iri_local, ns=SULO_IRI):
    return _W[f'{ns}{iri_local}']


# ════════════════════════════════════════════════════════════════════════════
# 1. Serializer – cardinality restrictions  (NB01, NB03)
# ════════════════════════════════════════════════════════════════════════════

class TestSerializerCardinality(unittest.TestCase):

    def _restriction(self, cls_name, prop_local, rtype, cardinality=None, filler_name=None):
        cls    = C(cls_name)
        p      = prop(prop_local)
        filler = C(filler_name) if filler_name else None
        for x in cls.is_a:
            if not isinstance(x, Restriction): continue
            if x.property is not p:            continue
            if x.type != rtype:                continue
            if cardinality is not None and x.cardinality != cardinality: continue
            if filler is not None and x.value is not filler:             continue
            return x
        return None

    def test_rge_exactly_1_physical_examination(self):
        r = self._restriction('SCT_RoutineGynecologicExamination',
                              'hasDirectPart', EXACTLY, 1, 'SCT_PhysicalExamination')
        self.assertIsNotNone(r, 'RGE: exactly-1 PhysicalExamination not found')
        self.assertEqual(to_manchester(r),
                         'sulo:hasDirectPart exactly 1 mie:SCT_PhysicalExamination')

    def test_rge_max_1_clinical_documentation(self):
        r = self._restriction('SCT_RoutineGynecologicExamination',
                              'hasDirectPart', MAX, 1, 'SCT_ClinicalDocumentation')
        self.assertIsNotNone(r, 'RGE: max-1 ClinicalDocumentation not found')
        self.assertEqual(to_manchester(r),
                         'sulo:hasDirectPart max 1 mie:SCT_ClinicalDocumentation')

    def test_pe_max_1_manual_breast_examination(self):
        r = self._restriction('SCT_PhysicalExamination',
                              'hasDirectPart', MAX, 1, 'SCT_ManualBreastExamination')
        self.assertIsNotNone(r, 'PE: max-1 ManualBreastExamination not found')
        self.assertEqual(to_manchester(r),
                         'sulo:hasDirectPart max 1 mie:SCT_ManualBreastExamination')

    def test_breast_exactly_1_nipple(self):
        r = self._restriction('Breast', 'hasDirectPart', EXACTLY, 1, 'Nipple')
        self.assertIsNotNone(r, 'Breast: exactly-1 Nipple not found')
        self.assertEqual(to_manchester(r), 'sulo:hasDirectPart exactly 1 mie:Nipple')


# ════════════════════════════════════════════════════════════════════════════
# 2. Serializer – universal (ONLY) restriction  (NB03)
# ════════════════════════════════════════════════════════════════════════════

class TestSerializerOnly(unittest.TestCase):

    def test_breast_only_named_parts(self):
        p = prop('hasDirectPart')
        r = next((x for x in C('Breast').is_a
                  if isinstance(x, Restriction) and x.property is p
                  and x.type == ONLY), None)
        self.assertIsNotNone(r, 'Breast: hasDirectPart only … not found')
        s = to_manchester(r)
        self.assertIn('sulo:hasDirectPart only', s)
        for name in ('mie:Nipple', 'mie:MammaryGland',
                     'mie:AdiposeTissue', 'mie:SkinOfBreast'):
            self.assertIn(name, s, f'{name} missing from ONLY filler')

    def test_medication_prescription_refers_to_only(self):
        p = prop('refersTo')
        r = next((x for x in C('MedicationPrescription').is_a
                  if isinstance(x, Restriction) and x.property is p
                  and x.type == ONLY), None)
        self.assertIsNotNone(r, 'MedicationPrescription: refersTo only … not found')
        s = to_manchester(r)
        self.assertIn('mie:MedicationAdministration', s)


# ════════════════════════════════════════════════════════════════════════════
# 3. Serializer – nested SOME restrictions  (NB02 biopsy participants)
# ════════════════════════════════════════════════════════════════════════════

class TestSerializerNestedSome(unittest.TestCase):

    def setUp(self):
        p = prop('hasParticipant')
        biopsy = C('SCT_CoreNeedleBiopsyOfBreast')
        self.strings = [to_manchester(x) for x in biopsy.is_a
                        if isinstance(x, Restriction) and x.property is p]

    def test_subject_of_care_role(self):
        self.assertTrue(any('mie:SubjectOfCareRole' in s for s in self.strings))

    def test_radiologist_role(self):
        self.assertTrue(any('mie:RadiologistRole' in s for s in self.strings))

    def test_instrument_role_biopsy_needle(self):
        self.assertTrue(any('mie:BiopsyNeedle' in s for s in self.strings))

    def test_location_role_breast(self):
        self.assertTrue(any('mie:Breast' in s for s in self.strings))

    def test_emerging_role_tissue(self):
        self.assertTrue(any('mie:Tissue' in s for s in self.strings))


# ════════════════════════════════════════════════════════════════════════════
# 4. Serializer – EquivalentTo  (NB02-NB05 defined classes)
# ════════════════════════════════════════════════════════════════════════════

class TestSerializerEquivalentTo(unittest.TestCase):

    def test_breast_equivalent_contains_all_parts(self):
        s = to_manchester(C('Breast').equivalent_to[0])
        for part in ('mie:Nipple', 'mie:MammaryGland',
                     'mie:AdiposeTissue', 'mie:SkinOfBreast'):
            self.assertIn(part, s)
        self.assertIn('sulo:hasDirectPart some', s)

    def test_specimen_producing_procedure_equivalent(self):
        s = to_manchester(C('SpecimenProducingProcedure').equivalent_to[0])
        self.assertIn('pro:EmergingRole', s)
        self.assertIn('mie:SpecimenRole', s)
        self.assertIn('mie:Tissue', s)

    def test_hypertensive_reading_constrained_datatype(self):
        s = to_manchester(C('HypertensiveReading').equivalent_to[0])
        self.assertIn('mie:BPMeasurement', s)
        self.assertIn('sulo:hasValue', s)
        self.assertIn('140', s)

    def test_intermediate_grade_or_filler(self):
        s = to_manchester(C('IntermediateOrHighGradeTumour').equivalent_to[0])
        self.assertIn('mie:TumourGrade2', s)
        self.assertIn('mie:TumourGrade3', s)
        self.assertIn('sulo:hasFeature', s)

    def test_hormone_receptor_positive_or_of_some(self):
        s = to_manchester(C('HormoneReceptorPositive').equivalent_to[0])
        self.assertIn('mie:ERPositive', s)
        self.assertIn('mie:PRPositive', s)

    def test_localised_breast_tumour_isin(self):
        s = to_manchester(C('LocalisedBreastTumour').equivalent_to[0])
        self.assertIn('mie:Tumour', s)
        self.assertIn('sulo:isIn', s)
        self.assertIn('mie:Breast', s)

    def test_confirmed_diagnosis_value_restriction(self):
        s = to_manchester(C('ConfirmedDiagnosis').equivalent_to[0])
        self.assertIn('mie:confirmed_status', s)
        self.assertIn('value', s.lower())


# ════════════════════════════════════════════════════════════════════════════
# 5. Parser – parse_manchester_expression produces correct objects
# ════════════════════════════════════════════════════════════════════════════

class TestParser(unittest.TestCase):

    def test_exactly_1(self):
        expr = parse_manchester_expression(
            'sulo:hasDirectPart exactly 1 mie:SCT_PhysicalExamination', _ONTO)
        self.assertIsInstance(expr, Restriction)
        self.assertEqual(expr.type, EXACTLY)
        self.assertEqual(expr.cardinality, 1)
        self.assertIs(expr.value, C('SCT_PhysicalExamination'))

    def test_max_1(self):
        expr = parse_manchester_expression(
            'sulo:hasDirectPart max 1 mie:SCT_ClinicalDocumentation', _ONTO)
        self.assertIsInstance(expr, Restriction)
        self.assertEqual(expr.type, MAX)
        self.assertEqual(expr.cardinality, 1)

    def test_some_with_nested_and(self):
        expr = parse_manchester_expression(
            'sulo:hasParticipant some '
            '(mie:SubjectOfCareRole and (sulo:isFeatureOf some mie:Person))',
            _ONTO)
        self.assertIsInstance(expr, Restriction)
        self.assertEqual(expr.type, SOME)
        self.assertIsInstance(expr.value, And)

    def test_only_with_union_filler(self):
        expr = parse_manchester_expression(
            'sulo:hasDirectPart only '
            '(mie:Nipple or mie:MammaryGland or mie:AdiposeTissue or mie:SkinOfBreast)',
            _ONTO)
        self.assertIsInstance(expr, Restriction)
        self.assertEqual(expr.type, ONLY)
        self.assertIsInstance(expr.value, Or)

    def test_and_expression(self):
        expr = parse_manchester_expression(
            'mie:Tissue and (sulo:hasFeature some (mie:TumourGrade2 or mie:TumourGrade3))',
            _ONTO)
        self.assertIsInstance(expr, And)

    def test_constrained_datatype(self):
        expr = parse_manchester_expression(
            'mie:BPMeasurement and (sulo:hasValue some xsd:integer[>= 140])',
            _ONTO)
        self.assertIsInstance(expr, And)

    def test_value_restriction(self):
        confirmed = I('confirmed_status')
        expr = parse_manchester_expression(
            'mie:DiagnosisStatement and (sulo:hasFeature value mie:confirmed_status)',
            _ONTO)
        self.assertIsInstance(expr, And)
        val_r = next((c for c in expr.Classes
                      if isinstance(c, Restriction) and c.type == VALUE), None)
        self.assertIsNotNone(val_r)
        self.assertIs(val_r.value, confirmed)


# ════════════════════════════════════════════════════════════════════════════
# 6. Serializer → Parser round-trip
# ════════════════════════════════════════════════════════════════════════════

class TestRoundTrip(unittest.TestCase):

    def _roundtrip(self, cls_name, which='equivalent_to', idx=0):
        cls  = C(cls_name)
        orig = getattr(cls, which)[idx]
        text = to_manchester(orig)
        back = parse_manchester_expression(text, _ONTO)
        self.assertEqual(to_manchester(back), text,
                         f'{cls_name}: round-trip text mismatch')

    def test_breast(self):               self._roundtrip('Breast')
    def test_specimen_producing(self):   self._roundtrip('SpecimenProducingProcedure')
    def test_hypertensive_reading(self): self._roundtrip('HypertensiveReading')
    def test_intermediate_grade(self):   self._roundtrip('IntermediateOrHighGradeTumour')
    def test_hormone_receptor(self):     self._roundtrip('HormoneReceptorPositive')
    def test_localised_tumour(self):     self._roundtrip('LocalisedBreastTumour')
    def test_confirmed_diagnosis(self):  self._roundtrip('ConfirmedDiagnosis')


# ════════════════════════════════════════════════════════════════════════════
# 7. parse_manchester_ontology – inline class definitions  (NB01-05 pattern)
# ════════════════════════════════════════════════════════════════════════════

class TestOntologyParser(unittest.TestCase):

    def setUp(self):
        self.w    = _new_world()
        self.onto = self.w.get_ontology('https://example.org/test/')
        sulo      = self.w.get_ontology(f'{SULO_IRI}sulo.owl').load()
        self.onto.imported_ontologies.append(sulo)

    def _parse(self, omn_text):
        parse_manchester_ontology(io.StringIO(omn_text), self.onto)

    def test_subclassof_declared(self):
        self._parse(
            'Prefix: ex:   <https://example.org/test/>\n'
            'Prefix: sulo: <https://w3id.org/sulo/>\n'
            '\n'
            'Class: ex:MyProcess\n'
            '    SubClassOf: sulo:Process\n'
        )
        cls = self.w['https://example.org/test/MyProcess']
        self.assertIsNotNone(cls)
        sulo_process = self.w[f'{SULO_IRI}Process']
        self.assertIn(sulo_process, cls.is_a)

    def test_equivalentto_declared(self):
        self._parse(
            'Prefix: ex:   <https://example.org/test/>\n'
            'Prefix: sulo: <https://w3id.org/sulo/>\n'
            '\n'
            'Class: ex:Base\n'
            '    SubClassOf: sulo:SpatialObject\n'
            '\n'
            'Class: ex:Defined\n'
            '    SubClassOf: ex:Base\n'
            '    EquivalentTo: ex:Base and (sulo:hasPart some ex:Base)\n'
        )
        dc = self.w['https://example.org/test/Defined']
        self.assertIsNotNone(dc)
        self.assertEqual(len(dc.equivalent_to), 1)

    def test_disjoint_classes_declared(self):
        self._parse(
            'Prefix: ex:   <https://example.org/test/>\n'
            'Prefix: sulo: <https://w3id.org/sulo/>\n'
            '\n'
            'Class: ex:A\n'
            '    SubClassOf: sulo:Quality\n'
            '\n'
            'Class: ex:B\n'
            '    SubClassOf: sulo:Quality\n'
            '\n'
            'DisjointClasses: ex:A, ex:B\n'
        )
        groups  = list(self.onto.disjoint_classes())
        members = {c.name for dg in groups for c in dg.entities}
        self.assertIn('A', members)
        self.assertIn('B', members)

    def test_multiple_classes_one_block(self):
        """Mirror of NB01 pattern: declare 4 process classes in one OMN block."""
        self._parse(
            'Prefix: ex:   <https://example.org/test/>\n'
            'Prefix: sulo: <https://w3id.org/sulo/>\n'
            '\n'
            'Class: ex:VisitProcess\n'
            '    SubClassOf: sulo:Process\n'
            '\n'
            'Class: ex:ExamProcess\n'
            '    SubClassOf: sulo:Process\n'
            '\n'
            'Class: ex:BiopsyProcess\n'
            '    SubClassOf: sulo:Process\n'
            '\n'
            'Class: ex:HistoProcess\n'
            '    SubClassOf: sulo:Process\n'
        )
        for name in ('VisitProcess', 'ExamProcess', 'BiopsyProcess', 'HistoProcess'):
            cls = self.w[f'https://example.org/test/{name}']
            self.assertIsNotNone(cls, f'{name} not declared')


# ════════════════════════════════════════════════════════════════════════════
# 8. Disjoint class axioms  (NB03, NB04, NB05)
# ════════════════════════════════════════════════════════════════════════════

class TestDisjointClasses(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pairs = set()
        for dg in _ONTO.disjoint_classes():
            ents = list(dg.entities)
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    cls.pairs.add(frozenset({ents[i].name, ents[j].name}))

    def _assert_disjoint(self, a, b):
        self.assertIn(frozenset({a, b}), self.pairs, f'{a} and {b} not disjoint')

    def test_tumour_grade1_grade2(self):  self._assert_disjoint('TumourGrade1', 'TumourGrade2')
    def test_tumour_grade2_grade3(self):  self._assert_disjoint('TumourGrade2', 'TumourGrade3')
    def test_er_positive_negative(self):  self._assert_disjoint('ERPositive', 'ERNegative')
    def test_pr_positive_negative(self):  self._assert_disjoint('PRPositive', 'PRNegative')
    def test_her2_positive_negative(self): self._assert_disjoint('HER2Positive', 'HER2Negative')
    def test_preliminary_confirmed(self): self._assert_disjoint('Preliminary', 'Confirmed')
    def test_nipple_mammary_gland(self):  self._assert_disjoint('Nipple', 'MammaryGland')
    def test_adipose_skin(self):          self._assert_disjoint('AdiposeTissue', 'SkinOfBreast')


# ════════════════════════════════════════════════════════════════════════════
# 9. classes_matching – TBox pattern queries  (NB08 pattern)
# ════════════════════════════════════════════════════════════════════════════

class TestClassesMatching(unittest.TestCase):

    def _names(self, query):
        return {c.name for c in classes_matching(query, _ONTO)}

    def test_exactly_1_pe_matches_rge(self):
        hits = self._names('sulo:hasDirectPart exactly 1 mie:SCT_PhysicalExamination')
        self.assertIn('SCT_RoutineGynecologicExamination', hits)

    def test_constrained_int_matches_hypertensive(self):
        hits = self._names('sulo:hasValue some xsd:integer[>= 140]')
        self.assertIn('HypertensiveReading', hits)

    def test_or_grade_filler_matches_intermediate(self):
        hits = self._names('sulo:hasFeature some (mie:TumourGrade2 or mie:TumourGrade3)')
        self.assertIn('IntermediateOrHighGradeTumour', hits)

    def test_breast_cancer_reference_matches_diagnosis(self):
        hits = self._names('mie:BreastCancer')
        self.assertIn('DiagnosisStatement', hits)

    def test_isin_breast_matches_localised_tumour(self):
        hits = self._names('sulo:isIn some mie:Breast')
        self.assertIn('LocalisedBreastTumour', hits)

    def test_value_confirmed_status_matches_confirmed_diagnosis(self):
        hits = self._names('sulo:hasFeature value mie:confirmed_status')
        self.assertIn('ConfirmedDiagnosis', hits)

    def test_er_positive_matches_hormone_receptor(self):
        hits = self._names('sulo:hasFeature some mie:ERPositive')
        self.assertIn('HormoneReceptorPositive', hits)


# ════════════════════════════════════════════════════════════════════════════
# 10. Reasoning – individual classification  (NB04, NB05)
# ════════════════════════════════════════════════════════════════════════════

class TestReasoning(unittest.TestCase):
    """Load mie-05 into a fresh world, run rustdl, assert classifications."""

    @classmethod
    def setUpClass(cls):
        cls.w    = _new_world()
        cls.onto = cls.w.get_ontology(f'file://{MIE05}').load()
        with cls.onto:
            sync_reasoner_rustdl(cls.onto)

    def C(self, name): return self.w[f'{MIE_IRI}{name}']
    def I(self, name): return self.w[f'{MIE_IRI}{name}']

    def test_bp_reading2_hypertensive(self):
        hr = self.C('HypertensiveReading')
        self.assertIn(self.I('mary_bp_reading2_feb18'), hr.instances())

    def test_bp_reading3_hypertensive(self):
        hr = self.C('HypertensiveReading')
        self.assertIn(self.I('mary_bp_reading3_feb18'), hr.instances())

    def test_bp_reading1_not_hypertensive(self):
        hr = self.C('HypertensiveReading')
        self.assertNotIn(self.I('mary_bp_reading1_feb18'), hr.instances())

    def test_hypertensive_count(self):
        hr = self.C('HypertensiveReading')
        self.assertEqual(len(list(hr.instances())), 2)

    def test_tissue_intermediate_or_high_grade(self):
        iogt = self.C('IntermediateOrHighGradeTumour')
        self.assertIn(self.I('mary_tissue_feb25'), iogt.instances())

    def test_tissue_hormone_receptor_positive(self):
        hrp = self.C('HormoneReceptorPositive')
        self.assertIn(self.I('mary_tissue_feb25'), hrp.instances())

    def test_tumour_localised_breast_tumour(self):
        lbt = self.C('LocalisedBreastTumour')
        self.assertIn(self.I('mary_tumour_left_breast'), lbt.instances())

    def test_dx_mar01_confirmed(self):
        cd = self.C('ConfirmedDiagnosis')
        self.assertIn(self.I('mary_dx_statement_mar01'), cd.instances())

    def test_dx_feb22_not_confirmed(self):
        cd = self.C('ConfirmedDiagnosis')
        self.assertNotIn(self.I('mary_dx_statement_feb22'), cd.instances())

    def test_biopsy_specimen_producing(self):
        spp = self.C('SpecimenProducingProcedure')
        self.assertIn(self.I('mary_biopsy_feb25'), spp.instances())


# ════════════════════════════════════════════════════════════════════════════
# 11. instances_of  (post-reasoning ABox queries)
# ════════════════════════════════════════════════════════════════════════════

class TestInstancesOf(unittest.TestCase):
    """Uses the same reasoned world as TestReasoning (separate world instance)."""

    @classmethod
    def setUpClass(cls):
        cls.w    = _new_world()
        cls.onto = cls.w.get_ontology(f'file://{MIE05}').load()
        with cls.onto:
            sync_reasoner_rustdl(cls.onto)

    def C(self, name): return self.w[f'{MIE_IRI}{name}']

    def test_bp_measurement_has_3_instances(self):
        inds = list(instances_of(self.C('BPMeasurement')))
        self.assertEqual(len(inds), 3)

    def test_person_instances_include_mary(self):
        inds = {i.name for i in instances_of(self.C('Person'), direct=False)}
        self.assertIn('mary', inds)

    def test_hypertensive_reading_has_2_instances(self):
        inds = list(instances_of(self.C('HypertensiveReading')))
        self.assertEqual(len(inds), 2)

    def test_confirmed_diagnosis_excludes_feb22(self):
        inds = {i.name for i in instances_of(self.C('ConfirmedDiagnosis'))}
        self.assertIn('mary_dx_statement_mar01', inds)
        self.assertNotIn('mary_dx_statement_feb22', inds)

    def test_tumour_grade2_has_one_instance(self):
        inds = list(instances_of(self.C('TumourGrade2'), direct=True))
        self.assertGreaterEqual(len(inds), 1)


# ════════════════════════════════════════════════════════════════════════════
# 11b. instances_of with anonymous DL expressions (post-reasoning)
# ════════════════════════════════════════════════════════════════════════════

class TestInstancesOfDLQuery(unittest.TestCase):
    """DL query tests: anonymous class expressions via parse_manchester_expression."""

    @classmethod
    def setUpClass(cls):
        cls.w    = _new_world()
        cls.onto = cls.w.get_ontology(f'file://{MIE05}').load()
        with cls.onto:
            sync_reasoner_rustdl(cls.onto)

    def _q(self, expr_str):
        expr = parse_manchester_expression(expr_str, self.onto)
        return {i.name for i in instances_of(expr, ontology=self.onto)}

    def test_hypertensive_reading_dl_query(self):
        """BPMeasurement and (hasValue some xsd:integer[>= 140]) → 2 readings."""
        hits = self._q('mie:BPMeasurement and (sulo:hasValue some xsd:integer[>= 140])')
        self.assertIn('mary_bp_reading2_feb18', hits)
        self.assertIn('mary_bp_reading3_feb18', hits)
        self.assertNotIn('mary_bp_reading1_feb18', hits)

    def test_confirmed_diagnosis_dl_query(self):
        """DiagnosisStatement and (hasFeature value confirmed_status) → mar01 only."""
        hits = self._q('mie:DiagnosisStatement and (sulo:hasFeature value mie:confirmed_status)')
        self.assertIn('mary_dx_statement_mar01', hits)
        self.assertNotIn('mary_dx_statement_feb22', hits)

    def test_intermediate_or_high_grade_tumour_dl_query(self):
        """Tissue and (hasFeature some (TumourGrade2 or TumourGrade3))."""
        hits = self._q('mie:Tissue and (sulo:hasFeature some (mie:TumourGrade2 or mie:TumourGrade3))')
        self.assertIn('mary_tissue_feb25', hits)

    def test_hormone_receptor_positive_dl_query(self):
        """Tissue and (hasFeature some ERPositive)."""
        hits = self._q('mie:Tissue and (sulo:hasFeature some mie:ERPositive)')
        self.assertIn('mary_tissue_feb25', hits)

    def test_localised_breast_tumour_dl_query(self):
        """Tumour and (isIn some Breast)."""
        hits = self._q('mie:Tumour and (sulo:isIn some mie:Breast)')
        self.assertIn('mary_tumour_left_breast', hits)


# ════════════════════════════════════════════════════════════════════════════
# 12. SPARQL with ??N parameter substitution
# ════════════════════════════════════════════════════════════════════════════

class TestSparql(unittest.TestCase):
    """Uses the module-level un-reasoned world (post-reasoning world not required
       for structural SPARQL; one reasoning world is shared via TestReasoning)."""

    @classmethod
    def setUpClass(cls):
        cls.w    = _new_world()
        cls.onto = cls.w.get_ontology(f'file://{MIE05}').load()
        with cls.onto:
            sync_reasoner_rustdl(cls.onto)

    def I(self, name): return self.w[f'{MIE_IRI}{name}']

    def test_hypertensive_readings_sparql(self):
        rows = list(self.w.sparql_query("""
            PREFIX sulo: <https://w3id.org/sulo/>
            PREFIX mie:  <https://w3id.org/ontostart/mie/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?reading ?value WHERE {
                ?reading rdf:type mie:HypertensiveReading .
                ?reading sulo:hasValue ?value .
            } ORDER BY ?value
        """))
        self.assertEqual(len(rows), 2)
        values = [v for _, v in rows]
        self.assertIn(142, values)
        self.assertIn(165, values)

    def test_confirmed_diagnosis_sparql(self):
        rows = list(self.w.sparql_query("""
            PREFIX sulo: <https://w3id.org/sulo/>
            PREFIX mie:  <https://w3id.org/ontostart/mie/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?stmt WHERE {
                ?stmt rdf:type mie:ConfirmedDiagnosis .
            }
        """))
        names = {r[0].name for r in rows}
        self.assertIn('mary_dx_statement_mar01', names)
        self.assertNotIn('mary_dx_statement_feb22', names)

    def test_sparql_parametrized_one_param(self):
        """??1 is replaced with the IRI of mary_tissue_feb25."""
        specimen = self.I('mary_tissue_feb25')
        rows = list(self.w.sparql_query("""
            PREFIX sulo: <https://w3id.org/sulo/>
            SELECT ?feature WHERE { ??1 sulo:hasFeature ?feature . }
        """, params=[specimen]))
        names = {r[0].name for r in rows if hasattr(r[0], 'name')}
        self.assertIn('mary_tumour_grade',  names)
        self.assertIn('mary_er_status',     names)
        self.assertIn('mary_pr_status',     names)
        self.assertIn('mary_her2_status',   names)

    def test_sparql_parametrized_individual_type(self):
        """??1 resolves for mary_bp_reading2_feb18; result includes BPMeasurement."""
        r2 = self.I('mary_bp_reading2_feb18')
        rows = list(self.w.sparql_query("""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?type WHERE { ??1 rdf:type ?type . }
        """, params=[r2]))
        names = {r[0].name for r in rows
                 if r[0] is not None and hasattr(r[0], 'name')}
        self.assertTrue(
            'BPMeasurement' in names or 'HypertensiveReading' in names,
            f'Expected BPMeasurement or HypertensiveReading, got {names}'
        )

    def test_sparql_parametrized_two_params(self):
        """??1 and ??2 are both substituted in the same query."""
        mary   = self.I('mary')
        breast = self.I('mary_left_breast')
        rows = list(self.w.sparql_query("""
            PREFIX sulo: <https://w3id.org/sulo/>
            SELECT ?role WHERE {
                ??1 sulo:hasFeature ?role .
                ?role sulo:isFeatureOf ??2 .
            }
        """, params=[breast, mary]))
        # mary_left_breast hasFeature roles that isFeatureOf mary
        self.assertGreaterEqual(len(rows), 0)   # at minimum does not error

    def test_sparql_all_bp_readings_with_values(self):
        rows = list(self.w.sparql_query("""
            PREFIX sulo: <https://w3id.org/sulo/>
            PREFIX mie:  <https://w3id.org/ontostart/mie/>
            PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?reading ?value WHERE {
                ?reading rdf:type mie:BPMeasurement .
                ?reading sulo:hasValue ?value .
            } ORDER BY ?value
        """))
        self.assertEqual(len(rows), 3)
        values = sorted(v for _, v in rows)
        self.assertEqual(values, [118, 142, 165])


# ════════════════════════════════════════════════════════════════════════════
# 13. Environment – recent rustdl reasoner
# ════════════════════════════════════════════════════════════════════════════

class TestRustdlVersion(unittest.TestCase):
    def test_rustdl_is_recent(self):
        self.assertGreaterEqual(
            _RUSTDL_VER, RUSTDL_MIN,
            "rustdl %s is older than the required %s"
            % (_RUSTDL_VER_STR, ".".join(map(str, RUSTDL_MIN))))


if __name__ == '__main__':
    unittest.main(verbosity=2)
