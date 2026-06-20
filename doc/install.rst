Owlready3 Installation
======================

Owlready3 can be installed with 'pip', the Python Package Installer.

Owlready3 include an optimized Cython module. This module speeds up by about 20% the loading of large ontologies,
but its use is entirely optional.
To build this module, you need a C compiler, and to install the 'cython' Python package.

On the contrary, if you don't have a C compiler, to **not build** the optimized module you need to uninstall
Cython if it is already installed (or to use the manual installation described below).

Owlready3 can be installed from terminal, from Python, or manually.


Optional backends (extras)
--------------------------

The core install has no third-party dependencies. Reasoning and the rdflib/SPARQL bridge are
loosely-coupled, opt-in backends, installed via extras::

   pip install owlready3                 # core only
   pip install owlready3[reasoning]      # + rustdl   -> sync_reasoner()
   pip install owlready3[rdflib]         # + rdflib   -> World.as_rdflib_graph() / sparql()
   pip install owlready3[all]            # rustdl + rdflib

See :doc:`integration` for how Owlready3 works together with rustdl (reasoning) and omny
(persistent store + SPARQL querying).


Installation from terminal (Bash under Linux or DOS under Windows)
------------------------------------------------------------------

You can use the following Bash / DOS commands to install Owlready3 in a terminal:

::

   pip install owlready3

.. figure:: _images/terminal_installation.png

   
If you don't have the permissions for writing in system files,
you can install Owlready3 in your user directory with this command:

::

   pip install --user owlready3



Installation in Spyder / IDLE (or any other Python console)
-----------------------------------------------------------

You can use the following Python commands to install Owlready3 from a Python 3.7.x console
(including those found in Spyder3 or IDLE):

::

   >>> import sys, subprocess
   >>> subprocess.run([sys.executable, "-m", "pip", "install", "--user", "owlready3"])

.. figure:: _images/spyder_installation.png

   
Manual installation
-------------------

Owlready3 can also be installed manually in 3 steps:

# Uncompress the Owlready3 source release file (Owlready3-x.y.tar.gz), for example in C:\\ under Windows

# Rename the directory C:\\Owlready3-x.y as C:\\owlready3

# Add the C:\\ directory in your PYTHONPATH; this can be done in Python as follows:

  ::

     import sys
     sys.path.append("C:\")
     import owlready3


In the following screenshot, I used /home/jiba/src instead of C:\\, under Linux:

.. figure:: _images/manual_installation.png
