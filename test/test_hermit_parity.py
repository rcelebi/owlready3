# -*- coding: utf-8 -*-
# Owlready3
#
# HermiT parity + runtime guard for the native rustdl reasoner.
#
# Validates that rustdl agrees with HermiT — the reference OWL 2 DL reasoner —
# on the decidable, consistent fragment of the MIE breast-cancer ontology:
# identical class subsumptions (transitive closure) and identical per-individual
# realization. Also records reasoning runtimes so regressions stay visible.
#
# Skipped unless rustdl + rdflib are installed AND `robot` (which bundles HermiT)
# is on PATH. Run it explicitly with:
#
#     python3 owlready3/test/test_hermit_parity.py -v
#
# Input fixture
# -------------
# `mie_dl_consistent.ofn` is a committed, self-contained OWL Functional Syntax
# file: the import-flattened MIE export, sanitized to be valid OWL 2 DL AND
# consistent so HermiT will reason over it. HermiT *rejects* the raw ontology;
# the sanitization (documented here for provenance) is:
#   * dropped TransitiveObjectProperty(hasDirectPart) and (isDirectPartOf) so
#     hasDirectPart is a *simple* role — OWL 2 DL forbids number restrictions on
#     non-simple (transitive) roles, and the ontology puts max/exact-cardinality
#     on hasDirectPart;
#   * fixed malformed xsd:dateTime literals ("YYYY-MM-DD HH:MM:SS" -> "...T...");
#   * dropped the `hasValue only string|decimal` datatype ranges, which clash
#     with the integer/dateTime values (HermiT proves the raw ontology
#     INCONSISTENT via datatype reasoning; rustdl does no datatype reasoning and
#     reports it consistent — a known leniency, not exercised here).
#
# These three points are exactly where rustdl is more lenient than the OWL 2 DL
# spec; this test deliberately compares only the fragment where *both* reasoners
# run, so it measures rustdl's DL reasoning correctness, not its input checking.

import os, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # owlready3/
sys.path.insert(0, os.path.dirname(ROOT))         # claude-ws/ so "import owlready3" finds the local copy

FIXTURE = os.path.join(HERE, "mie_dl_consistent.ofn")

try:
  import rustdl
  _HAS_RUSTDL = True
except ImportError:
  _HAS_RUSTDL = False

try:
  import rdflib
  from rdflib.namespace import RDF, RDFS, OWL
  _HAS_RDFLIB = True
except ImportError:
  _HAS_RDFLIB = False

_ROBOT = shutil.which("robot")

OWL_THING   = "http://www.w3.org/2002/07/owl#Thing"
OWL_NOTHING = "http://www.w3.org/2002/07/owl#Nothing"

# Loose runtime ceilings — catch gross regressions / non-termination, not
# normal machine variance. Override with RUSTDL_PARITY_MAX_* if a slow CI box
# needs more headroom.
def _ceiling(env, default):
  try:    return float(os.environ.get(env, default))
  except ValueError: return default

MAX_CLASSIFY_SECS = _ceiling("RUSTDL_PARITY_MAX_CLASSIFY_SECS", 30.0)
MAX_REALIZE_SECS  = _ceiling("RUSTDL_PARITY_MAX_REALIZE_SECS", 900.0)


def _local(iri):
  return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _transitive_closure(edges):
  """Reflexive-free transitive closure of a set of (a, b) `a ⊑ b` edges."""
  from collections import defaultdict
  succ = defaultdict(set)
  for a, b in edges:
    succ[a].add(b)
  changed = True
  while changed:
    changed = False
    for a in list(succ):
      add = set()
      for b in succ[a]:
        add |= succ.get(b, set())
      if not add <= succ[a]:
        succ[a] |= add
        changed = True
  return {(a, b) for a in succ for b in succ[a] if a != b}


@unittest.skipUnless(
  _HAS_RUSTDL and _HAS_RDFLIB and _ROBOT and os.path.exists(FIXTURE),
  "needs rustdl + rdflib + robot (HermiT) on PATH + the MIE fixture")
class HermitParity(unittest.TestCase):
  # Populated once in setUpClass: HermiT and rustdl results + timings.
  hermit_secs = rustdl_classify_secs = rustdl_realize_secs = 0.0

  @classmethod
  def setUpClass(cls):
    # ---- HermiT (via ROBOT): classification + realization in one pass ----
    cls.hermit_out = os.path.join(tempfile.gettempdir(), "rustdl_hermit_parity.owl")
    t = time.time()
    proc = subprocess.run(
      [_ROBOT, "reason", "--reasoner", "hermit", "--input", FIXTURE,
       "--axiom-generators", "subclass classassertion", "--include-indirect", "true",
       "--output", cls.hermit_out],
      capture_output=True, text=True)
    cls.hermit_secs = time.time() - t
    if proc.returncode != 0:
      raise unittest.SkipTest("robot/HermiT could not reason over the fixture:\n%s"
                              % (proc.stderr or proc.stdout)[-400:])

    g = rdflib.Graph()
    g.parse(cls.hermit_out)
    named = {str(s) for s in g.subjects(RDF.type, OWL.Class) if isinstance(s, rdflib.URIRef)}
    named |= {OWL_THING, OWL_NOTHING}

    # HermiT subsumptions: subClassOf + equivalentClass (both directions), closed.
    edges = set()
    for s, _, o in g.triples((None, RDFS.subClassOf, None)):
      if isinstance(s, rdflib.URIRef) and isinstance(o, rdflib.URIRef):
        edges.add((str(s), str(o)))
    for s, _, o in g.triples((None, OWL.equivalentClass, None)):
      if isinstance(s, rdflib.URIRef) and isinstance(o, rdflib.URIRef):
        edges.add((str(s), str(o)))
        edges.add((str(o), str(s)))
    edges = {(a, b) for a, b in edges if a in named and b in named}
    cls.hermit_subs = {(a, b) for (a, b) in _transitive_closure(edges)
                       if b != OWL_THING and a != OWL_NOTHING}

    # HermiT realization: every inferred named rdf:type (indirect included).
    cls.hermit_types = {}
    for ind, _, c in g.triples((None, RDF.type, None)):
      if not (isinstance(ind, rdflib.URIRef) and isinstance(c, rdflib.URIRef)):
        continue
      cc = str(c)
      if cc in (str(OWL.NamedIndividual), OWL_THING) or cc not in named:
        continue
      cls.hermit_types.setdefault(str(ind), set()).add(cc)

    # ---- rustdl: classification + realization on the same fixture ----
    # per_pair_timeout_ms=0 => the unbounded/complete path, matching HermiT.
    t = time.time()
    cls.classification = rustdl.classify(FIXTURE, per_pair_timeout_ms=0)
    cls.rustdl_classify_secs = time.time() - t

    t = time.time()
    cls.most_specific = rustdl.realize(FIXTURE, per_pair_timeout_ms=0)
    cls.rustdl_realize_secs = time.time() - t

    classes = list(cls.classification.classes)
    cls.rustdl_subs = {(a, b) for a in classes for b in classes
                       if a != b and b != OWL_THING and a != OWL_NOTHING
                       and cls.classification.is_subclass(a, b)}

    # Close rustdl's most-specific types upward to all entailed named types.
    def supers(c):
      return {s for s in classes if s != c and s != OWL_THING
              and cls.classification.is_subclass(c, s)}
    cls.rustdl_types = {}
    for ind, types in cls.most_specific.items():
      allt = set()
      for c in types:
        allt.add(c)
        allt |= supers(c)
      cls.rustdl_types[ind] = {t for t in allt if t != OWL_THING}

    # Restrict both subsumption sets to the shared named-class vocabulary.
    vocab = set(classes) | {OWL_THING, OWL_NOTHING}
    cls.hermit_subs = {(a, b) for (a, b) in cls.hermit_subs if a in vocab and b in vocab}

  def test_consistency_agrees(self):
    # HermiT reasoned (didn't report inconsistent) => consistent; rustdl must agree.
    self.assertTrue(rustdl.is_consistent(FIXTURE),
                    "rustdl reports the fixture inconsistent but HermiT accepted it")

  def test_classification_parity(self):
    only_hermit = self.hermit_subs - self.rustdl_subs
    only_rustdl = self.rustdl_subs - self.hermit_subs
    self.assertEqual(set(), only_hermit,
                     "subsumptions HermiT found but rustdl missed (UNSOUND/incomplete): %s"
                     % sorted((_local(a), _local(b)) for a, b in only_hermit)[:20])
    self.assertEqual(set(), only_rustdl,
                     "subsumptions rustdl asserts but HermiT does not (UNSOUND): %s"
                     % sorted((_local(a), _local(b)) for a, b in only_rustdl)[:20])

  def test_realization_parity(self):
    inds = set(self.hermit_types) | set(self.rustdl_types)
    self.assertTrue(inds, "no individuals compared")
    mismatches = []
    for i in sorted(inds):
      h = self.hermit_types.get(i, set())
      r = self.rustdl_types.get(i, set())
      if h != r:
        mismatches.append((_local(i),
                           sorted(_local(x) for x in h - r),   # HermiT-only
                           sorted(_local(x) for x in r - h)))  # rustdl-only
    self.assertEqual([], mismatches,
                     "per-individual type sets differ from HermiT: %s" % mismatches[:10])

  def test_runtime_recorded(self):
    # Benchmark line (always printed) + loose regression ceilings.
    print("\n[HermiT-parity runtime] HermiT(reason)=%.2fs  rustdl.classify=%.3fs  "
          "rustdl.realize(complete)=%.2fs  | classes=%d individuals=%d subsumptions=%d"
          % (self.hermit_secs, self.rustdl_classify_secs, self.rustdl_realize_secs,
             len(self.classification.classes), len(self.rustdl_types), len(self.rustdl_subs)),
          file=sys.stderr)
    self.assertLess(self.rustdl_classify_secs, MAX_CLASSIFY_SECS,
                    "rustdl classification far slower than expected (regression?)")
    self.assertLess(self.rustdl_realize_secs, MAX_REALIZE_SECS,
                    "rustdl complete realization far slower than expected (regression / non-termination?)")


if __name__ == "__main__":
  unittest.main()
