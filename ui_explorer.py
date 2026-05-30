"""Owlready2 Explorer — Streamlit UI.

Run:
    streamlit run owlready2/ui_explorer.py
"""

import sys, os, subprocess, tempfile, time, traceback

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title="Owlready2 Explorer", page_icon="🦉", layout="wide")

# ── owlready2 ─────────────────────────────────────────────────────────────────
try:
    import owlready2 as owl
    from owlready2.manchester import parse_manchester_expression, instances_of, to_manchester
    owl.set_log_level(0)
except Exception as e:
    st.error(f"Cannot import owlready2: {e}")
    st.stop()

# ── session state ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    "selected_path": "",   # path chosen via Browse
    "last_browse_dir": os.path.expanduser("~"),  # remembered across Browse clicks
    "world":         None,
    "onto":          None,
    "reasoned":      False,
    "tmpfiles":      [],
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Auto-load a pre-built SQLite world cache (set OWL_SQLITE_CACHE env var).
_sqlite_cache = os.environ.get("OWL_SQLITE_CACHE", "")
if _sqlite_cache and st.session_state["onto"] is None:
    if os.path.isfile(_sqlite_cache):
        with st.spinner(f"Loading cached world from {_sqlite_cache} …"):
            try:
                w = owl.World()
                w.set_backend(filename=_sqlite_cache)
                n = w.graph.execute("SELECT COUNT(*) FROM objs").fetchone()[0]
                if n > 0:
                    onto_auto = next(iter(w.ontologies.values()), None)
                    if onto_auto is None:
                        onto_auto = w.get_ontology("http://auto-loaded/")
                    st.session_state["world"] = w
                    st.session_state["onto"]  = onto_auto
            except Exception as _e:
                st.warning(f"Auto-load failed: {_e}")

# Auto-load from an NT file (set OWL_NT_FILE env var).
# Uses sidecar SQLite cache so second launch is instant.
_nt_file = os.environ.get("OWL_NT_FILE", "")
if _nt_file and st.session_state["onto"] is None:
    if os.path.isfile(_nt_file):
        _sidecar = _nt_file + ".world.sqlite3"
        _from_cache = os.path.isfile(_sidecar)
        _msg = (f"Opening sidecar cache for {os.path.basename(_nt_file)} …"
                if _from_cache else
                f"Parsing {os.path.basename(_nt_file)} and building sidecar cache …")
        with st.spinner(_msg):
            try:
                w = owl.World()
                w.set_backend(filename=_sidecar)
                n = w.graph.execute("SELECT COUNT(*) FROM objs").fetchone()[0]
                if n > 100_000:
                    onto_auto = next(iter(w.ontologies.values()), None) or w.get_ontology("http://auto-loaded/")
                else:
                    with open(_nt_file, "rb") as _fobj:
                        onto_auto = w.get_ontology("http://auto-loaded/").load(
                            fileobj=_fobj, format="ntriples")
                    w.graph.commit()
                st.session_state["world"] = w
                st.session_state["onto"]  = onto_auto
            except Exception as _e:
                st.warning(f"NT auto-load failed: {_e}")


def _new_world():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    st.session_state["tmpfiles"].append(path)
    w = owl.World()
    w.set_backend(filename=path)
    return w


def _try_open_ox_store():
    """Open a persistent pyoxigraph store if one exists alongside the NT file."""
    if "ox_store" in st.session_state:
        return st.session_state["ox_store"]
    nt = os.environ.get("OWL_NT_FILE", "")
    sentinel = nt + ".ox_store/.ready" if nt else ""
    # Also check the default benchmark store location
    for sentinel_path, store_dir in [
        (sentinel, nt + ".ox_store") if nt else ("", ""),
        ("/tmp/snomed_ox_store/.ready", "/tmp/snomed_ox_store"),
    ]:
        if sentinel_path and os.path.exists(sentinel_path):
            try:
                import pyoxigraph as _ox
                store = _ox.Store(store_dir)
                st.session_state["ox_store"] = store
                return store
            except Exception:
                pass
    return None


# ── header ────────────────────────────────────────────────────────────────────
st.title("🦉 Owlready2 Explorer")
st.divider()

# ── STEP 1: Select & Load ─────────────────────────────────────────────────────
st.subheader("Step 1 — Select ontology")

col_browse, col_path, col_load = st.columns([1, 5, 1])

with col_browse:
    if st.button("📂 Browse", use_container_width=True):
        last_dir = st.session_state["last_browse_dir"]
        result = subprocess.run(
            ["osascript",
             "-e", "tell application \"System Events\" to activate",
             "-e", f"POSIX path of (choose file with prompt \"Select OWL file\" "
                   f"default location POSIX file \"{last_dir}\" "
                   f"of type {{\"owl\",\"rdf\",\"ttl\",\"omn\",\"ofn\",\"xml\",\"nt\",\"n3\"}})"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            chosen = result.stdout.strip()
            st.session_state["selected_path"]   = chosen
            st.session_state["path_display"]    = chosen   # syncs the text input widget
            st.session_state["last_browse_dir"] = os.path.dirname(chosen)
            st.rerun()

with col_path:
    st.text_input(
        "path", label_visibility="collapsed",
        placeholder="Click Browse or paste a file path here…",
        key="path_display",
    )
    st.session_state["selected_path"] = st.session_state.get("path_display", "")

with col_load:
    do_load = st.button(
        "Load", use_container_width=True, type="primary",
        disabled=not st.session_state["selected_path"].strip(),
    )

# ── load handler ──────────────────────────────────────────────────────────────
def _sqlite_cache_path_for(nt_path):
    """Return a sidecar SQLite cache path for an NT file."""
    return nt_path + ".world.sqlite3"

def _load_nt_fast(path):
    """Load an NT file using a sidecar SQLite cache.

    On first load: parses NT into a new SQLite world and persists it as a
    sidecar file next to the NT (path + '.world.sqlite3').  Subsequent loads
    reuse the sidecar directly, making them near-instant.
    """
    cache = _sqlite_cache_path_for(path)
    w = owl.World()
    w.set_backend(filename=cache)
    n = w.graph.execute("SELECT COUNT(*) FROM objs").fetchone()[0]
    if n > 100_000:
        onto = next(iter(w.ontologies.values()), None) or w.get_ontology("http://auto-loaded/")
        return w, onto, True   # (world, onto, from_cache)

    # Fresh parse — write into the sidecar so next open is instant
    with open(path, "rb") as fobj:
        iri  = "http://auto-loaded/" + os.path.basename(path) + "#"
        onto = w.get_ontology(iri).load(fileobj=fobj, format="ntriples")
    w.graph.commit()
    return w, onto, False

if do_load:
    path = st.session_state["selected_path"].strip()
    if not os.path.isfile(path):
        st.error(f"File not found: {path}")
    else:
        is_nt = path.lower().endswith((".nt", ".ntriples"))
        with st.spinner(f"Loading {os.path.basename(path)}…"):
            try:
                if is_nt:
                    w, onto, from_cache = _load_nt_fast(path)
                    if from_cache:
                        st.success("Loaded from sidecar SQLite cache — instant ⚡")
                    else:
                        cache = _sqlite_cache_path_for(path)
                        st.info(f"Parsed NT and saved cache → {cache}  (next load will be instant)")
                else:
                    file_dir = os.path.dirname(os.path.abspath(path))
                    if file_dir not in owl.onto_path:
                        owl.onto_path.append(file_dir)
                    w    = _new_world()
                    onto = w.get_ontology(f"file://{os.path.abspath(path)}").load()

                st.session_state["world"]    = w
                st.session_state["onto"]     = onto
                st.session_state["reasoned"] = False
            except Exception as e:
                st.error(f"Load failed: {e}")
                st.session_state["onto"] = None
        if st.session_state["onto"]:
            st.rerun()

# ── nothing loaded yet ────────────────────────────────────────────────────────
if st.session_state["onto"] is None:
    st.stop()

# ── ontology loaded ───────────────────────────────────────────────────────────
onto  = st.session_state["onto"]
world = st.session_state["world"]

st.divider()

# summary bar — compute counts once and cache in session state
if "onto_counts" not in st.session_state or st.session_state.get("onto_counts_for") is not onto:
    _w = st.session_state["world"]
    _n_cls  = _w.graph.execute("SELECT COUNT(DISTINCT s) FROM objs WHERE p=6").fetchone()[0]
    _n_ind  = _w.graph.execute("SELECT COUNT(DISTINCT s) FROM objs WHERE p=7").fetchone()[0]
    _n_prop = sum(1 for _ in onto.properties())
    st.session_state["onto_counts"]     = (_n_cls, _n_ind, _n_prop)
    st.session_state["onto_counts_for"] = onto
_n_cls, _n_ind, _n_prop = st.session_state["onto_counts"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Classes",     f"{_n_cls:,}")
c2.metric("Individuals", f"{_n_ind:,}")
c3.metric("Properties",  f"{_n_prop:,}")
c4.metric("Reasoned",    "✓ yes" if st.session_state["reasoned"] else "✗ no")

with st.expander(f"Loaded: `{onto.base_iri}`", expanded=False):
    col_unload, _ = st.columns([1, 5])
    if col_unload.button("Unload ontology", type="secondary"):
        st.session_state["world"]         = None
        st.session_state["onto"]          = None
        st.session_state["reasoned"]      = False
        st.session_state["selected_path"] = ""
        st.rerun()

st.divider()

# ── main tabs ─────────────────────────────────────────────────────────────────
tab_info, tab_reason, tab_axiom, tab_query, tab_sparql = st.tabs([
    "📋 Info", "⚙️ Reasoning", "✏️ Add Axiom", "🔍 DL Query", "🗄️ SPARQL"
])

# ══════════════════════════════════════════════════════════════════════════════
# Tab: Info
# ══════════════════════════════════════════════════════════════════════════════
with tab_info:
    _PAGE = 200

    st.markdown("**Classes**")
    i_col1, i_col2 = st.columns([3, 1])
    with i_col2:
        cls_page = st.number_input("Page", min_value=1, key="cls_page", step=1, label_visibility="collapsed")
    with i_col1:
        cls_filter = st.text_input("Filter by name", placeholder="fracture…", key="cls_filter",
                                   label_visibility="collapsed")
    _all_classes = list(onto.classes())
    if cls_filter.strip():
        _all_classes = [c for c in _all_classes if cls_filter.lower() in (c.name or "").lower()]
    _all_classes.sort(key=lambda c: c.name or "")
    _cls_slice = _all_classes[(_PAGE * (cls_page - 1)):(_PAGE * cls_page)]
    st.caption(f"Showing {len(_cls_slice)} of {len(_all_classes)} classes (page {cls_page})")
    if _cls_slice:
        st.dataframe(
            [{"Class": c.name, "IRI": c.iri,
              "SubClassOf": ", ".join(p.name for p in c.is_a
                                     if isinstance(p, type) and p is not owl.Thing)}
             for c in _cls_slice],
            use_container_width=True, hide_index=True,
        )

    st.markdown("**Properties**")
    props = list(onto.properties())
    obj_props  = [p for p in props if issubclass(type(p), owl.ObjectProperty)]
    data_props = [p for p in props if issubclass(type(p), owl.DataProperty)]
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.markdown("*Object properties*")
        for p in obj_props:
            st.markdown(f"- `{p.name}`")
    with pcol2:
        st.markdown("*Data properties*")
        for p in data_props:
            st.markdown(f"- `{p.name}`")

    inds = list(onto.individuals())
    if inds:
        st.markdown("**Individuals**")
        st.dataframe(
            [{"Individual": i.name, "IRI": i.iri,
              "Types": ", ".join(t.name for t in i.is_a if isinstance(t, type))}
             for i in sorted(inds, key=lambda i: i.name or "")[:_PAGE]],
            use_container_width=True, hide_index=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# Tab: Reasoning
# ══════════════════════════════════════════════════════════════════════════════
with tab_reason:
    r_col1, r_col2, r_col3 = st.columns([2, 2, 4])
    with r_col1:
        reasoner = st.selectbox("Reasoner", ["Pellet", "HermiT"])
    with r_col2:
        infer_props = st.checkbox("Infer property values", value=True)
    with r_col3:
        st.write("")   # vertical align

    if st.button("▶ Run Reasoner", type="primary"):
        with st.spinner(f"Running {reasoner}…"):
            try:
                t0 = time.time()
                with onto:
                    if reasoner == "Pellet":
                        owl.sync_reasoner_pellet(onto, infer_property_values=infer_props)
                    else:
                        owl.sync_reasoner_hermit(onto, infer_property_values=infer_props)
                elapsed = time.time() - t0
                st.session_state["reasoned"] = True
                st.success(f"{reasoner} finished in {elapsed:.2f}s")
                st.rerun()
            except Exception as e:
                st.error(f"Reasoning failed: {e}")

    if st.session_state["reasoned"]:
        st.info("Reasoning is complete. DL queries now reflect inferred classifications.")

# ══════════════════════════════════════════════════════════════════════════════
# Tab: Add Axiom
# ══════════════════════════════════════════════════════════════════════════════
with tab_axiom:
    axiom_mode = st.radio(
        "Axiom type",
        ["SubClassOf", "EquivalentTo", "Individual type assertion"],
        horizontal=True,
    )

    if axiom_mode in ("SubClassOf", "EquivalentTo"):
        a_col1, a_col2 = st.columns([1, 2])
        with a_col1:
            class_name = st.text_input("Class name", placeholder="e.g. Pizza")
        with a_col2:
            axiom_expr = st.text_input("Manchester expression",
                                       placeholder="e.g. hasTopping some VegetableTopping")
        if st.button("Add Axiom", type="primary"):
            try:
                cls_obj = world[onto.base_iri + class_name]
                if cls_obj is None:
                    raise ValueError(f"Class '{class_name}' not found.")
                expr = parse_manchester_expression(axiom_expr.strip(), onto)
                with onto:
                    if axiom_mode == "SubClassOf":
                        cls_obj.is_a.append(expr)
                    else:
                        cls_obj.equivalent_to.append(expr)
                st.success(f"{axiom_mode} axiom added to `{class_name}`.")
                st.session_state["reasoned"] = False
            except Exception as e:
                st.error(f"Error: {e}")

    else:
        b_col1, b_col2 = st.columns([1, 2])
        with b_col1:
            ind_name = st.text_input("Individual name", placeholder="e.g. my_pizza")
        with b_col2:
            ind_type = st.text_input("Type (Manchester expression)",
                                     placeholder="e.g. Pizza and (hasTopping some Cheese)")
        if st.button("Add Axiom", type="primary", key="btn_ind"):
            try:
                expr = parse_manchester_expression(ind_type.strip(), onto)
                with onto:
                    existing = world[onto.base_iri + ind_name]
                    if existing is None:
                        new_ind = owl.Thing(ind_name, namespace=onto)
                        new_ind.is_a.append(expr)
                    else:
                        existing.is_a.append(expr)
                st.success(f"Type assertion added to `{ind_name}`.")
                st.session_state["reasoned"] = False
            except Exception as e:
                st.error(f"Error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# Tab: DL Query
# ══════════════════════════════════════════════════════════════════════════════

import re as _re

_SCT_BASE = "http://snomed.info/id/"
_RDFS_SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"

def _expand_snomed_iris(text):
    """Expand sct:XXXXXXX and bare 6-18 digit SNOMED IDs to full IRIs."""
    text = _re.sub(r'\bsct:(\d+)\b', lambda m: f'<{_SCT_BASE}{m.group(1)}>', text)
    text = _re.sub(r'(?<![:\w<])(\d{6,18})(?![\w>])', lambda m: f'<{_SCT_BASE}{m.group(1)}>', text)
    return text


def _eval_dl(expr, world, ox_store, direct):
    """Evaluate a Manchester class expression over the flat-triple SNOMED model.

    Named class  → SQLite subClassOf index (.subclasses / .descendants)
    Restriction  → SPARQL on pyoxigraph (role triples are flat, not OWL BNodes)
    And / Or     → set intersection / union of recursive results
    Not inside And → complement via subtraction (no full-universe scan needed)
    Cardinality  → Python-side Counter (SPARQL HAVING not supported by pyoxigraph)
    """
    from owlready2.class_construct import Restriction, And, Or, Not
    from owlready2.base import SOME, VALUE, ONLY, MIN, MAX, EXACTLY
    from collections import Counter as _Counter

    if isinstance(expr, type):
        return set(expr.subclasses() if direct else expr.descendants())

    if isinstance(expr, And):
        # Split positive and Not terms; avoid full-universe scan.
        pos = [e for e in expr.Classes if not isinstance(e, Not)]
        neg = [e.Class for e in expr.Classes if isinstance(e, Not)]
        if pos:
            result = _eval_dl(pos[0], world, ox_store, direct)
            for e in pos[1:]:
                result &= _eval_dl(e, world, ox_store, direct)
        else:
            result = set(world.classes())
        for e in neg:
            result -= _eval_dl(e, world, ox_store, direct)
        return result

    if isinstance(expr, Or):
        result = set()
        for e in expr.Classes:
            result |= _eval_dl(e, world, ox_store, direct)
        return result

    if isinstance(expr, Not):
        return set(world.classes()) - _eval_dl(expr.Class, world, ox_store, direct)

    if isinstance(expr, Restriction):
        if ox_store is None:
            raise RuntimeError("Role restrictions require the pyoxigraph store.")
        prop_iri = expr.property.iri
        rtype    = expr.type

        if rtype == VALUE:
            q = f"SELECT DISTINCT ?s WHERE {{ ?s <{prop_iri}> <{expr.value.iri}> }}"
            return {c for r in ox_store.query(q) if (c := world.get(r[0].value)) is not None}

        if rtype == SOME:
            filler = expr.value
            if filler is owl.Thing or not isinstance(filler, type):
                q = f"SELECT DISTINCT ?s WHERE {{ ?s <{prop_iri}> ?v }}"
            else:
                q = f"SELECT DISTINCT ?s WHERE {{ ?s <{prop_iri}> <{filler.iri}> }}"
            return {c for r in ox_store.query(q) if (c := world.get(r[0].value)) is not None}

        if rtype in (MIN, MAX, EXACTLY):
            n = expr.cardinality
            counts = _Counter(r[0].value for r in ox_store.query(
                f"SELECT ?s ?v WHERE {{ ?s <{prop_iri}> ?v }}"))
            if rtype == MIN:
                iris = [iri for iri, cnt in counts.items() if cnt >= n]
            elif rtype == MAX:
                iris = [iri for iri, cnt in counts.items() if cnt <= n]
            else:
                iris = [iri for iri, cnt in counts.items() if cnt == n]
            return {c for iri in iris if (c := world.get(iri)) is not None}

        raise NotImplementedError(f"Restriction type {rtype} not supported")

    raise NotImplementedError(f"Cannot evaluate {type(expr).__name__}")

with tab_query:
    q_col1, q_col2, q_col3 = st.columns([4, 1, 1])
    with q_col1:
        dl_expr = st.text_input(
            "Manchester class expression",
            placeholder="e.g.  sct:404684003   or   <http://snomed.info/id/404684003>",
            key="dl_expr",
        )
    with q_col2:
        query_mode = st.selectbox("Return", ["Subclasses", "Individuals"], key="dl_mode")
    with q_col3:
        st.write("")
        direct = st.checkbox("Direct only", key="dl_direct")

    st.caption(
        "**Tip:** use `sct:404684003` or a bare SNOMED ID — both are expanded to full IRIs automatically. "
        "Use `<full IRI>` for non-SNOMED terms. "
        "**Subclasses** mode works for any class; **Individuals** mode requires owl:NamedIndividual instances."
    )

    if st.button("▶ Run Query", type="primary", disabled=not dl_expr.strip()):
        try:
            expanded = _expand_snomed_iris(dl_expr.strip())
            expr     = parse_manchester_expression(expanded, onto)
            parsed   = to_manchester(expr)
            st.markdown(f"**Parsed:** `{parsed}`")

            if query_mode == "Individuals":
                results = instances_of(expr, direct=direct, ontology=onto)
                st.markdown(f"**{len(results):,} individual(s) found**")
                if results:
                    rows = [{"Individual": ind.name, "IRI": ind.iri,
                             "Types": ", ".join(t.name for t in ind.is_a if isinstance(t, type))}
                            for ind in sorted(results, key=lambda i: i.name or "")]
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.info("No individuals match. Try **Subclasses** mode — SNOMED uses owl:Class, not individuals.")

            else:  # Subclasses / complex DL
                ox = _try_open_ox_store()
                t0 = time.time()
                hits = sorted(_eval_dl(expr, world, ox, direct),
                              key=lambda c: getattr(c, "name", "") or "")
                elapsed = time.time() - t0
                st.markdown(f"**{len(hits):,} class(es) matched** in {elapsed:.2f}s")
                _LIMIT = 1000
                st.dataframe(
                    [{"Class": getattr(h, "name", repr(h)),
                      "Label": str(next(iter(h.label), "")) if h.label else "",
                      "IRI":   getattr(h, "iri", "")}
                     for h in hits[:_LIMIT]],
                    use_container_width=True, hide_index=True,
                )
                if len(hits) > _LIMIT:
                    st.caption(f"Showing first {_LIMIT:,} of {len(hits):,}")
        except NotImplementedError as e:
            st.error(f"Not supported: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    st.markdown("##### Subclass / superclass lookup")
    sc_col1, sc_col2, sc_col3 = st.columns([3, 2, 1])
    with sc_col1:
        sc_name = st.text_input("Class name", placeholder="e.g. Pizza", key="sc_name")
    with sc_col2:
        sc_dir = st.selectbox("Direction", ["Subclasses", "Superclasses"])
    with sc_col3:
        st.write("")
        do_sc = st.button("Run", key="btn_sc")

    if do_sc and sc_name.strip():
        try:
            _term = sc_name.strip()
            # Try IRI-based lookup first, then fall back to label / name search
            cls_obj = (world.get(_term)
                       or world.get(onto.base_iri + _term)
                       or next((c for c in onto.classes()
                                 if (c.name or "").lower() == _term.lower()
                                 or any(_term.lower() in str(l).lower()
                                        for l in (c.label or []))), None))
            if cls_obj is None:
                st.error(f"Class '{_term}' not found. Try an IRI fragment or rdfs:label substring.")
            else:
                hits = list(cls_obj.subclasses()) if sc_dir == "Subclasses" \
                    else [a for a in cls_obj.ancestors() if a is not cls_obj]
                st.markdown(f"**{len(hits)} result(s) for `{cls_obj.name}`:**")
                st.dataframe(
                    [{"Class": getattr(h, "name", repr(h)), "IRI": getattr(h, "iri", "")}
                     for h in sorted(hits, key=lambda c: getattr(c, "name", "") or "")[:500]],
                    use_container_width=True, hide_index=True,
                )
                if len(hits) > 500:
                    st.caption(f"Showing first 500 of {len(hits)}")
        except Exception as e:
            st.error(f"Error: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# Tab: SPARQL
# ══════════════════════════════════════════════════════════════════════════════
with tab_sparql:
    _default_sparql = (
        "PREFIX owl:  <http://www.w3.org/2002/07/owl#>\n"
        "PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\n"
        "SELECT ?cls WHERE {\n"
        "  ?cls rdf:type owl:Class .\n"
        "} LIMIT 20"
    )
    sparql_text = st.text_area("SPARQL query", value=_default_sparql, height=180)

    if st.button("▶ Run SPARQL", type="primary", disabled=not sparql_text.strip()):
        try:
            import pyoxigraph as _ox

            # Resolve pyoxigraph store — prefer pre-built persistent store,
            # fall back to building one from the current world's SQLite backend.
            ox = _try_open_ox_store()
            _store_label = "persistent ox_store"
            _use_union   = False
            if ox is None:
                if hasattr(world.graph, "_store"):          # tripleoxigraph backend
                    ox          = world.graph._store
                    _use_union  = True                       # triples live in named graphs
                    _store_label = "tripleoxigraph RocksDB store"
                else:
                    graph        = world.as_sparql_graph()
                    ox           = graph._get_cached_store()
                    _store_label = "in-memory pyoxigraph store (built from SQLite)"

            st.caption(f"Querying: {_store_label}")

            def _cell(v):
                if v is None:                      return ""
                if isinstance(v, _ox.NamedNode):   return v.value
                if isinstance(v, _ox.Literal):     return str(v.value)
                if isinstance(v, _ox.BlankNode):   return f"_:{v.value}"
                return str(v)

            t0  = time.time()
            raw = list(ox.query(sparql_text, use_default_graph_as_union=_use_union))
            elapsed = time.time() - t0

            st.markdown(f"**{len(raw)} row(s)** in {elapsed:.3f}s")
            if raw:
                first = raw[0]
                if hasattr(first, "_fields"):
                    cols = list(first._fields)
                    rows = [{c: _cell(getattr(r, c)) for c in cols} for r in raw]
                else:
                    cols = [f"col{i}" for i in range(len(first))]
                    rows = [{c: _cell(r[i]) for i, c in enumerate(cols)} for r in raw]
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("No results.")
        except Exception as e:
            st.error(f"Error: {e}")
