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


def _new_world():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    st.session_state["tmpfiles"].append(path)
    w = owl.World()
    w.set_backend(filename=path)
    return w


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
if do_load:
    path = st.session_state["selected_path"].strip()
    if not os.path.isfile(path):
        st.error(f"File not found: {path}")
    else:
        with st.spinner(f"Loading {os.path.basename(path)}…"):
            try:
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

# summary bar
c1, c2, c3, c4 = st.columns(4)
c1.metric("Classes",     len(list(onto.classes())))
c2.metric("Individuals", len(list(onto.individuals())))
c3.metric("Properties",  len(list(onto.properties())))
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
    classes = sorted(onto.classes(),     key=lambda c: c.name or "")
    inds    = sorted(onto.individuals(), key=lambda i: i.name or "")
    props   = sorted(onto.properties(),  key=lambda p: p.name or "")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Classes**")
        for c in classes:
            parents = [p.name for p in c.is_a
                       if isinstance(p, type) and p is not owl.Thing]
            sup = f" ⊑ {', '.join(parents)}" if parents else ""
            st.markdown(f"- `{c.name}`{sup}")

    with col_b:
        st.markdown("**Individuals**")
        for ind in inds:
            types = [t.name for t in ind.is_a if isinstance(t, type)]
            st.markdown(f"- `{ind.name}` : {', '.join(types) or 'owl:Thing'}")

    st.markdown("**Properties**")
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
with tab_query:
    if not st.session_state["reasoned"]:
        st.warning("Run the reasoner first (⚙️ Reasoning tab) for inferred results.")

    q_col1, q_col2 = st.columns([5, 1])
    with q_col1:
        dl_expr = st.text_input(
            "Manchester class expression",
            placeholder="e.g. Pizza and (hasTopping some Cheese)",
            key="dl_expr",
        )
    with q_col2:
        st.write("")
        direct = st.checkbox("Direct only")

    if st.button("▶ Run Query", type="primary", disabled=not dl_expr.strip()):
        try:
            expr    = parse_manchester_expression(dl_expr.strip(), onto)
            parsed  = to_manchester(expr)
            results = instances_of(expr, direct=direct, ontology=onto)

            st.markdown(f"**Parsed:** `{parsed}`")
            st.markdown(f"**{len(results)} individual(s) found**")

            if results:
                rows = []
                for ind in sorted(results, key=lambda i: i.name or ""):
                    types = [t.name for t in ind.is_a
                             if isinstance(t, type) and t is not owl.Thing]
                    rows.append({
                        "Individual": ind.name,
                        "IRI":        ind.iri,
                        "Types":      ", ".join(types) or "owl:Thing",
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("No individuals match this expression.")
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
            cls_obj = world[onto.base_iri + sc_name.strip()]
            if cls_obj is None:
                st.error(f"Class '{sc_name}' not found.")
            else:
                hits = list(cls_obj.subclasses()) if sc_dir == "Subclasses" \
                    else [a for a in cls_obj.ancestors() if a is not cls_obj]
                st.markdown(f"**{len(hits)} result(s):**")
                for h in sorted(hits, key=lambda c: getattr(c, "name", "") or ""):
                    st.markdown(f"- `{getattr(h, 'name', repr(h))}`")
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
    s_col1, s_col2 = st.columns([2, 3])
    with s_col1:
        owlready_conv = st.checkbox("Convert to owlready2 objects", value=True)
    with s_col2:
        st.write("")

    if st.button("▶ Run SPARQL", type="primary", disabled=not sparql_text.strip()):
        try:
            graph = world.as_sparql_graph()
            t0    = time.time()
            raw   = list(graph.query_owlready(sparql_text) if owlready_conv
                         else graph.query(sparql_text))
            elapsed = time.time() - t0

            st.markdown(f"**{len(raw)} row(s)** in {elapsed:.3f}s")
            if raw:
                first = raw[0]
                cols  = list(first._fields) if hasattr(first, "_fields") \
                    else [f"col{i}" for i in range(len(first))]

                def _cell(v):
                    if v is None:            return ""
                    if hasattr(v, "iri"):    return v.iri
                    if hasattr(v, "name"):   return v.name
                    return str(v)

                rows = [
                    {c: _cell(getattr(r, c) if hasattr(r, "_fields") else r[i])
                     for i, c in enumerate(cols)}
                    for r in raw
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("No results.")
        except Exception as e:
            st.error(f"Error: {e}")
