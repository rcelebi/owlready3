"""
Run regtest.py with the oxigraph backend.
Patches BaseTest.new_world() to create OxigraphGraph worlds.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Import regtest module (the exec-based approach won't work with unittest discovery)
import importlib.util
spec = importlib.util.spec_from_file_location("regtest", os.path.join(os.path.dirname(__file__), "regtest.py"))
rt = importlib.util.module_from_spec(spec)
sys.modules["regtest"] = rt

# Patch new_world BEFORE the module executes
import owlready2 as _owl
import tempfile

def _new_world_oxigraph(self):
    w = _owl.World()
    w.set_backend("oxigraph")
    return w

# Execute the regtest module
spec.loader.exec_module(rt)

# Patch after load
rt.BaseTest.new_world = _new_world_oxigraph

import unittest
loader = unittest.TestLoader()
suite  = loader.loadTestsFromModule(rt)
runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
