"""Owlready3 Explorer — Streamlit UI.

Stack:
  • owlready3 — ontology load / edit / Manchester parsing (SQLite-backed World)
  • rustdl    — native OWL 2 DL (SROIQ) reasoner, via sync_reasoner_rustdl()
  • omny      — store-agnostic SPARQL helper; queries run through World.sparql()
                (SELECT) or World.as_rdflib_graph() (CONSTRUCT / ASK / DESCRIBE)

Run:
    streamlit run owlready3/ui_explorer.py     # from the directory above the package
    # or:  PYTHONPATH=.. streamlit run ui_explorer.py

Query paths:
  Path A — owlready3 Python API (SQLite): .classes()/.subclasses()/.descendants(),
           Manchester parse + instances_of / classes_matching.
  Path B — omny + SPARQL: omny builds store-agnostic SPARQL; omny.store.run_*
           executes it against the live World (no Owlready3 internals touched).
"""

import sys, os, subprocess, tempfile, time

# Make `import owlready3` work whether launched from inside or above the package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title="Owlready3 Explorer", page_icon="🦉", layout="wide")

try:
    import owlready3 as owl
    from owlready3.manchester import (
        parse_manchester_expression, instances_of, classes_matching, to_manchester,
    )
    owl.set_log_level(0)
except Exception as e:
    st.error(f"Cannot import owlready3: {e}")
    st.stop()

try:
    import omny
    from omny.store import run_owlready2 as omny_run_select, run_rdflib as omny_run_rdflib
    _HAS_OMNY = True
except Exception as _e:
    _HAS_OMNY = False
    _OMNY_ERR = str(_e)

try:
    import owlready3.reasoning as _reasoning
    _HAS_RUSTDL = _reasoning._load_rustdl() is not None
    _RUSTDL_ERR = ""
except Exception as _e:
    _HAS_RUSTDL = False
    _RUSTDL_ERR = str(_e)

# ── constants ─────────────────────────────────────────────────────────────────
_DISPLAY_CAP = 1_000
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# ── session state defaults ────────────────────────────────────────────────────
for k, v in {
    "selected_path":   "",
    "last_browse_dir": os.path.expanduser("~"),
    "world":           None,
    "onto":            None,
    "reasoned":        False,
    "consistent":      None,
    "tmpfiles":        [],
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _local(term):
    """Local name from an IRI / Owlready entity / rdflib-or-pyoxigraph term."""
    iri = getattr(term, "iri", None) or getattr(term, "value", None) or str(term)
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _cell(v):
    if v is None:
        return ""
    return getattr(v, "value", None) or getattr(v, "iri", None) or str(v)


def _new_world():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    st.session_state["tmpfiles"].append(path)
    w = owl.World()
    w.set_backend(filename=path)
    return w


def _entity_rows(entities, limit=_DISPLAY_CAP):
    rows = []
    for h in list(entities)[:limit]:
        rows.append({
            "Name":  getattr(h, "name", repr(h)),
            "Label": str(next(iter(getattr(h, "label", []) or []), "")),
            "IRI":   getattr(h, "iri", ""),
        })
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🦉 Owlready3 Explorer")
st.caption("owlready3 · rustdl reasoner · omny SPARQL")

# status chips
s1, s2 = st.columns(2)
s1.markdown(("✅ **rustdl** reasoner available" if _HAS_RUSTDL
             else f"⚠️ **rustdl** not available — {_RUSTDL_ERR}"))
s2.markdown(("✅ **omny** SPARQL available" if _HAS_OMNY
             else f"⚠️ **omny** not available — {_OMNY_ERR}"))
st.divider()

# ── Step 1: Select & Load ─────────────────────────────────────────────────────
st.subheader("Step 1 — Select ontology")
col_browse, col_path, col_load = st.columns([1, 5, 1])

with col_browse:
    if st.button("📂 Browse", use_container_width=True):
        if sys.platform == "darwin":
            result = subprocess.run(
                ["osascript",
                 "-e", 'tell application "System Events" to activate',
                 "-e", (f'POSIX path of (choose file with prompt "Select OWL file" '
                        f'default location POSIX file "{st.session_state["last_browse_dir"]}")')],
                capture_output=True, text=True)
            if result.returncode == 0:
                chosen = result.stdout.strip()
                st.session_state["path_display"]    = chosen
                st.session_state["last_browse_dir"] = os.path.dirname(chosen)
                st.rerun()
        else:
            st.info("Browse dialog is macOS-only — paste a path instead.")

with col_path:
    st.text_input("path", label_visibility="collapsed",
                  placeholder="Paste a file path (.owl .rdf .ttl .ofn .nt …) or click Browse",
                  key="path_display")
    st.session_state["selected_path"] = st.session_state.get("path_display", "")

with col_load:
    do_load = st.button("Load", use_container_width=True, type="primary",
                        disabled=not st.session_state["selected_path"].strip())

with st.expander("…or build a tiny demo ontology"):
    if st.button("🍕 Load pizza demo"):
        w = _new_world()
        demo = w.get_ontology("http://example.org/pizza.owl")
        with demo:
            class Pizza(owl.Thing): pass
            class VegetarianPizza(Pizza): pass
            class Margherita(VegetarianPizza): pass
            class hasTopping(owl.ObjectProperty): pass
            class Topping(owl.Thing): pass
            class CheeseTopping(Topping): pass
        st.session_state.update(world=w, onto=demo, reasoned=False, consistent=None)
        st.rerun()

if do_load:
    path = st.session_state["selected_path"].strip()
    if not os.path.isfile(path):
        st.error(f"File not found: {path}")
    else:
        with st.spinner(f"Loading {os.path.basename(path)} …"):
            try:
                w = _new_world()
                if path.lower().endswith((".nt", ".ntriples")):
                    with open(path, "rb") as fobj:
                        onto = w.get_ontology(
                            "http://auto-loaded/" + os.path.basename(path) + "#"
                        ).load(fileobj=fobj, format="ntriples")
                    w.graph.commit()
                else:
                    file_dir = os.path.dirname(os.path.abspath(path))
                    if file_dir not in owl.onto_path:
                        owl.onto_path.append(file_dir)
                    onto = w.get_ontology(f"file://{os.path.abspath(path)}").load()
                st.session_state.update(world=w, onto=onto, reasoned=False, consistent=None)
            except Exception as e:
                st.error(f"Load failed: {e}")
                st.session_state["onto"] = None
        if st.session_state["onto"]:
            st.rerun()

if st.session_state["onto"] is None:
    st.stop()

onto  = st.session_state["onto"]
world = st.session_state["world"]
st.divider()

# ── Summary bar ───────────────────────────────────────────────────────────────
n_cls  = sum(1 for _ in onto.classes())
n_ind  = sum(1 for _ in onto.individuals())
n_prop = sum(1 for _ in onto.properties())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Classes",     f"{n_cls:,}")
c2.metric("Individuals", f"{n_ind:,}")
c3.metric("Properties",  f"{n_prop:,}")
_reasoned_label = "✓ yes" if st.session_state["reasoned"] else "✗ no"
if st.session_state["consistent"] is False:
    _reasoned_label = "✗ inconsistent"
c4.metric("Reasoned", _reasoned_label)

with st.expander(f"Loaded: `{onto.base_iri}`", expanded=False):
    if st.button("Unload ontology", type="secondary"):
        st.session_state.update(world=None, onto=None, reasoned=False,
                                consistent=None, selected_path="", path_display="")
        st.rerun()

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_info, tab_reason, tab_axiom, tab_query, tab_sparql = st.tabs([
    "📋 Info", "⚙️ Reasoning (rustdl)", "✏️ Add Axiom", "🔍 DL Query", "🗄️ SPARQL (omny)",
])


# ══ Tab: Info ═════════════════════════════════════════════════════════════════
with tab_info:
    _PAGE = 200
    st.markdown("**Classes**")
    i_col1, i_col2 = st.columns([3, 1])
    with i_col2:
        cls_page = st.number_input("Page", min_value=1, key="cls_page", step=1,
                                   label_visibility="collapsed")
    with i_col1:
        cls_filter = st.text_input("Filter by name", placeholder="filter…",
                                   key="cls_filter", label_visibility="collapsed")
    all_cls = list(onto.classes())
    if cls_filter.strip():
        all_cls = [c for c in all_cls if cls_filter.lower() in (c.name or "").lower()]
    all_cls.sort(key=lambda c: c.name or "")
    _slice = all_cls[_PAGE * (cls_page - 1): _PAGE * cls_page]
    st.caption(f"Showing {len(_slice)} of {len(all_cls)} classes (page {cls_page})")
    if _slice:
        st.dataframe(
            [{"Class": c.name, "IRI": c.iri,
              "SubClassOf": ", ".join(p.name for p in c.is_a
                                      if isinstance(p, type) and p is not owl.Thing)}
             for c in _slice],
            use_container_width=True, hide_index=True)

    st.markdown("**Properties**")
    props      = list(onto.properties())
    obj_props  = [p for p in props if issubclass(type(p), owl.ObjectProperty)]
    data_props = [p for p in props if issubclass(type(p), owl.DataProperty)]
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.markdown("*Object properties*")
        for p in obj_props:  st.markdown(f"- `{p.name}`")
    with pcol2:
        st.markdown("*Data properties*")
        for p in data_props: st.markdown(f"- `{p.name}`")

    inds = list(onto.individuals())
    if inds:
        st.markdown("**Individuals**")
        st.dataframe(
            [{"Individual": i.name, "IRI": i.iri,
              "Types": ", ".join(t.name for t in i.is_a if isinstance(t, type))}
             for i in sorted(inds, key=lambda i: i.name or "")[:_PAGE]],
            use_container_width=True, hide_index=True)


# ══ Tab: Reasoning (rustdl) ═══════════════════════════════════════════════════
with tab_reason:
    st.markdown("Classify & realize with the native **rustdl** OWL 2 DL reasoner.")
    if not _HAS_RUSTDL:
        st.warning(f"rustdl is not available: {_RUSTDL_ERR}\n\n`pip install rustdl`")
    r_col1, r_col2, r_col3 = st.columns(3)
    with r_col1:
        infer_props = st.checkbox("Infer object property values", value=False)
    with r_col2:
        infer_data = st.checkbox("Infer data property values", value=False)
    with r_col3:
        saturation = st.checkbox("Saturation only (fast EL)", value=False,
                                 help="Fast EL-closure under-approximation.")

    if st.button("▶ Run rustdl", type="primary", disabled=not _HAS_RUSTDL):
        with st.spinner("Running rustdl …"):
            try:
                t0 = time.time()
                with onto:
                    owl.sync_reasoner_rustdl(
                        onto,
                        infer_property_values=infer_props,
                        infer_data_property_values=infer_data,
                        saturation_only=saturation,
                        debug=0,
                    )
                st.session_state.update(reasoned=True, consistent=True)
                st.success(f"rustdl finished in {time.time() - t0:.2f}s")
                st.rerun()
            except owl.OwlReadyInconsistentOntologyError as e:
                st.session_state.update(reasoned=True, consistent=False)
                st.error(f"Ontology is INCONSISTENT: {e}")
            except Exception as e:
                st.error(f"Reasoning failed: {type(e).__name__}: {e}")

    if st.session_state["reasoned"] and st.session_state["consistent"]:
        st.info("Reasoning complete — DL queries now reflect inferred classifications.")
        # Show classes equivalent to Nothing (unsatisfiable), if any.
        unsat = [c for c in onto.classes() if owl.Nothing in getattr(c, "equivalent_to", [])]
        if unsat:
            st.warning("Unsatisfiable classes: " + ", ".join(c.name for c in unsat))


# ══ Tab: Add Axiom ════════════════════════════════════════════════════════════
with tab_axiom:
    axiom_mode = st.radio("Axiom type",
                          ["SubClassOf", "EquivalentTo", "Individual type assertion"],
                          horizontal=True)

    if axiom_mode in ("SubClassOf", "EquivalentTo"):
        a_col1, a_col2 = st.columns([1, 2])
        with a_col1:
            class_name = st.text_input("Class name", placeholder="e.g. Pizza")
        with a_col2:
            axiom_expr = st.text_input("Manchester expression",
                                       placeholder="e.g. hasTopping some CheeseTopping")
        if st.button("Add Axiom", type="primary"):
            try:
                cls_obj = world[onto.base_iri + class_name] or onto[class_name]
                if cls_obj is None:
                    raise ValueError(f"Class '{class_name}' not found.")
                expr = parse_manchester_expression(axiom_expr.strip(), onto)
                with onto:
                    if axiom_mode == "SubClassOf":
                        cls_obj.is_a.append(expr)
                    else:
                        cls_obj.equivalent_to.append(expr)
                st.success(f"{axiom_mode} axiom added to `{class_name}`.")
                st.session_state.update(reasoned=False, consistent=None)
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        b_col1, b_col2 = st.columns([1, 2])
        with b_col1:
            ind_name = st.text_input("Individual name", placeholder="e.g. my_pizza")
        with b_col2:
            ind_type = st.text_input("Type (Manchester expression)",
                                     placeholder="e.g. Pizza and (hasTopping some CheeseTopping)")
        if st.button("Add Axiom", type="primary", key="btn_ind"):
            try:
                expr = parse_manchester_expression(ind_type.strip(), onto)
                with onto:
                    existing = world[onto.base_iri + ind_name]
                    if existing is None:
                        owl.Thing(ind_name, namespace=onto).is_a.append(expr)
                    else:
                        existing.is_a.append(expr)
                st.success(f"Type assertion added to `{ind_name}`.")
                st.session_state.update(reasoned=False, consistent=None)
            except Exception as e:
                st.error(f"Error: {e}")


# ══ Tab: DL Query ═════════════════════════════════════════════════════════════
with tab_query:
    q_col1, q_col2, q_col3 = st.columns([4, 1, 1])
    with q_col1:
        dl_expr = st.text_input("Manchester class expression",
                                placeholder="e.g. VegetarianPizza   or   hasTopping some CheeseTopping",
                                key="dl_expr")
    with q_col2:
        query_mode = st.selectbox("Return", ["Subclasses", "Individuals"], key="dl_mode")
    with q_col3:
        st.write("")
        direct = st.checkbox("Direct only", key="dl_direct")

    if st.button("▶ Run Query", type="primary", disabled=not dl_expr.strip()):
        try:
            text = dl_expr.strip()
            expr = parse_manchester_expression(text, onto)
            st.markdown(f"**Parsed:** `{to_manchester(expr)}`")
            t0 = time.time()

            if query_mode == "Subclasses":
                if isinstance(expr, type):
                    hits = (list(expr.subclasses()) if direct else list(expr.descendants()))
                else:
                    # Complex class expression → owlready3 manchester matcher.
                    hits = list(classes_matching(text, onto))
            else:
                hits = list(instances_of(expr, direct=direct, ontology=onto))

            elapsed = time.time() - t0
            hits = sorted({h for h in hits}, key=lambda h: getattr(h, "name", "") or "")
            noun = "class(es)" if query_mode == "Subclasses" else "individual(s)"
            st.markdown(f"**{len(hits):,} {noun} matched** in {elapsed:.3f}s")

            rows = _entity_rows(hits)
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
                if len(hits) > _DISPLAY_CAP:
                    st.caption(f"Showing first {_DISPLAY_CAP:,} of {len(hits):,}")
            else:
                st.info("No results.")
        except NotImplementedError as e:
            st.error(f"Not supported: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    st.markdown("##### Class relations via omny")
    st.caption("omny builds a store-agnostic SPARQL query; it runs through World.sparql().")
    rc1, rc2, rc3 = st.columns([3, 2, 1])
    with rc1:
        rel_name = st.text_input("Class name or IRI", placeholder="e.g. Pizza", key="rel_name")
    with rc2:
        rels = st.multiselect("Relations", ["super", "sub", "equiv"],
                              default=["super", "sub", "equiv"], key="rel_kinds")
    with rc3:
        st.write("")
        do_rel = st.button("Run", key="btn_rel", disabled=not _HAS_OMNY)

    if do_rel and rel_name.strip():
        try:
            term = rel_name.strip()
            cls_obj = (world.get(term) or world.get(onto.base_iri + term) or onto[term])
            target = cls_obj if cls_obj is not None else f"<{term}>"
            q = omny.class_relations_query(target, relations=tuple(rels) or ("super", "sub", "equiv"),
                                           construct=False)
            with st.expander("Generated SPARQL", expanded=False):
                st.code(q, language="sparql")
            names = sorted({_local(row[0]) for row in omny_run_select(q, world)})
            st.markdown(f"**{len(names)} related term(s):**")
            st.dataframe([{"Term": n} for n in names], use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error: {e}")


# ══ Tab: SPARQL (omny) ════════════════════════════════════════════════════════
with tab_sparql:
    st.caption("SELECT runs through omny.store.run_owlready2 (World.sparql); "
               "CONSTRUCT/ASK/DESCRIBE run through omny.store.run_rdflib (World.as_rdflib_graph).")
    _default = (
        "PREFIX owl:  <http://www.w3.org/2002/07/owl#>\n"
        "PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n\n"
        "SELECT ?cls WHERE {\n"
        "  ?cls rdf:type owl:Class .\n"
        "} LIMIT 50"
    )
    sparql_text = st.text_area("SPARQL query", value=_default, height=200)

    if st.button("▶ Run SPARQL", type="primary",
                 disabled=not (sparql_text.strip() and _HAS_OMNY)):
        try:
            t0 = time.time()
            head = sparql_text.lstrip().upper()
            # Strip leading PREFIX/BASE lines to find the query form.
            for line in sparql_text.splitlines():
                ls = line.strip().upper()
                if ls and not ls.startswith(("PREFIX", "BASE", "#")):
                    head = ls
                    break

            if head.startswith("SELECT"):
                rows_raw = list(omny_run_select(sparql_text, world))
                elapsed = time.time() - t0
                st.markdown(f"**{len(rows_raw):,} row(s)** in {elapsed:.3f}s")
                if rows_raw:
                    width = max(len(r) for r in rows_raw)
                    cols = [f"col{i}" for i in range(width)]
                    st.dataframe(
                        [{cols[i]: _cell(r[i]) for i in range(len(r))} for r in rows_raw],
                        use_container_width=True, hide_index=True)
                else:
                    st.info("No results.")
            else:
                result = omny_run_rdflib(sparql_text, world.as_rdflib_graph())
                elapsed = time.time() - t0
                import rdflib
                if isinstance(result, rdflib.Graph):
                    st.markdown(f"**{len(result):,} triple(s)** in {elapsed:.3f}s")
                    st.dataframe(
                        [{"s": _cell(s), "p": _cell(p), "o": _cell(o)}
                         for s, p, o in list(result)[:_DISPLAY_CAP]],
                        use_container_width=True, hide_index=True)
                else:
                    st.markdown(f"**Result** in {elapsed:.3f}s")
                    st.write(result)
        except Exception as e:
            st.error(f"Error: {type(e).__name__}: {e}")
