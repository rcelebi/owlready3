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

VERSION = "0.25"

from owlready3.base            import *

from owlready3.namespace       import *
from owlready3.entity          import *
from owlready3.prop            import *
from owlready3.prop            import _FUNCTIONAL_FOR_CACHE
from owlready3.individual      import *
from owlready3.class_construct import *
from owlready3.disjoint        import *
from owlready3.annotation      import *
from owlready3.reasoning       import *
from owlready3.reasoning       import _keep_most_specific
from owlready3.close           import *

import owlready3.namespace, owlready3.entity, owlready3.prop, owlready3.class_construct, owlready3.triplelite
owlready3.triplelite.Or                     = Or
owlready3.namespace.EntityClass             = EntityClass
owlready3.namespace.ThingClass              = ThingClass
owlready3.namespace.PropertyClass           = PropertyClass
owlready3.namespace.AnnotationPropertyClass = AnnotationPropertyClass
owlready3.namespace.ObjectPropertyClass     = ObjectPropertyClass
owlready3.namespace.DataPropertyClass       = DataPropertyClass
owlready3.namespace.ObjectProperty          = ObjectProperty
owlready3.namespace.DataProperty            = DataProperty
owlready3.namespace.AnnotationProperty      = AnnotationProperty
owlready3.namespace.Thing                   = Thing
owlready3.namespace.Property                = Property
owlready3.namespace.Or                      = Or
owlready3.namespace.And                     = And
owlready3.namespace.Not                     = Not
owlready3.namespace.Restriction             = Restriction
owlready3.namespace.OneOf                   = OneOf
owlready3.namespace.FusionClass             = FusionClass
owlready3.namespace.AllDisjoint             = AllDisjoint
owlready3.namespace.ConstrainedDatatype     = ConstrainedDatatype
owlready3.namespace.Inverse                 = Inverse
owlready3.namespace.IndividualValueList     = IndividualValueList
owlready3.entity.Thing              = Thing
owlready3.entity.Nothing            = Nothing
owlready3.entity.Construct          = Construct
owlready3.entity.And                = And
owlready3.entity.Or                 = Or
owlready3.entity.Not                = Not
owlready3.entity.OneOf              = OneOf
owlready3.entity.Restriction        = Restriction
owlready3.entity.ObjectPropertyClass= ObjectPropertyClass
owlready3.entity.ObjectProperty     = ObjectProperty
owlready3.entity.DataProperty       = DataProperty
owlready3.entity.AnnotationProperty = AnnotationProperty
owlready3.entity.ReasoningPropertyClass = ReasoningPropertyClass
owlready3.entity.FunctionalProperty = FunctionalProperty
#owlready3.entity.ValueList          = ValueList
owlready3.entity.AllDisjoint        = AllDisjoint
owlready3.entity.Inverse            = Inverse
owlready3.entity._FUNCTIONAL_FOR_CACHE = _FUNCTIONAL_FOR_CACHE
owlready3.entity._property_value_restrictions = owlready3.prop._property_value_restrictions
owlready3.entity._inherited_properties_value_restrictions = owlready3.prop._inherited_properties_value_restrictions
owlready3.disjoint.Or = Or
owlready3.prop.Restriction             = Restriction
owlready3.prop.ConstrainedDatatype     = ConstrainedDatatype
owlready3.prop.Construct               = Construct
owlready3.prop.AnnotationProperty      = AnnotationProperty
owlready3.prop.Thing                   = Thing
owlready3.prop.PropertyChain           = PropertyChain
owlready3.prop._check_superclasses     = True

owlready3.prop.ThingClass              = ThingClass
owlready3.prop.And                     = And
owlready3.prop.Or                      = Or
owlready3.prop.OneOf                   = OneOf
owlready3.annotation.Construct         = Construct

owlready3.individual._keep_most_specific = _keep_most_specific
owlready3.individual.Construct           = Construct
owlready3.individual.TransitiveProperty  = TransitiveProperty
owlready3.individual.SymmetricProperty   = SymmetricProperty
owlready3.individual.ReflexiveProperty   = ReflexiveProperty
owlready3.individual.InverseFunctionalProperty = InverseFunctionalProperty
owlready3.individual.AnnotationPropertyClass   = AnnotationPropertyClass
owlready3.class_construct.Thing       = Thing
owlready3.class_construct.ThingClass  = ThingClass
owlready3.class_construct.EntityClass = EntityClass

del owlready3

from owlready3.rule            import *

import owlready3.manchester
from owlready3.manchester import (to_manchester, manchester_render_ontology,
                                  parse_manchester_expression,
                                  parse_manchester_ontology,
                                  instances_of, classes_matching)

LOADING.__exit__()

# Not real property
del owl_world._props["Property"]
del owl_world._props["ObjectProperty"]
del owl_world._props["DatatypeProperty"]
del owl_world._props["FunctionalProperty"]
del owl_world._props["InverseFunctionalProperty"]
del owl_world._props["TransitiveProperty"]
del owl_world._props["SymmetricProperty"]
del owl_world._props["AsymmetricProperty"]
del owl_world._props["ReflexiveProperty"]
del owl_world._props["IrreflexiveProperty"]
del owl_world._props["AnnotationProperty"]

default_world = IRIS = World()
get_ontology  = default_world.get_ontology
get_namespace = default_world.get_namespace


def default_render_func(entity):
  if isinstance(entity.storid, int) and (entity.storid < 0): return "_:%s" % (-entity.storid)
  return "%s.%s" % (entity.namespace.name, entity.name)

def set_render_func(func):
  type.__setattr__(EntityClass, "__repr__", func)
  type.__setattr__(Thing      , "__repr__", func)
  
set_render_func(default_render_func)
