#!/usr/bin/python
"""
medication.py

Defines the Medication and ParsedMedication classes. Medication represents a 
single line from the medication lists to reconcile; ParsedMedication is a 
subclass of Medication that decomposes a line according to regexps (see
constants.py)

Created by Jorge Herskovic 
Copyright (c) 2011 UTHealth School of Biomedical Informatics. All rights reserved.
"""

import re
from decimal import *
import copy
import logging
import operator
from constants import *

medication_parser = re.compile(r"""^\s*(?P<name>.*?)
                                  \s+(?P<dose>[0-9\.\/]+)
                                  \s+(?P<units>m?c?k?g|m?d?l)
                                  \s*(?P<formulation>.*?)
                                  ;
                                  \s*?(?P<instructions>.*)""",
                                  re.IGNORECASE | re.VERBOSE)

def _sequential_id_gen(starting=0):
    while True:
        yield starting
        starting += 1

_sequential_id=_sequential_id_gen()

class MappingContextError(Exception): pass

class Medication(object):
    """Represents a single medication from a list to be reconciled."""
    def __init__(self, original_string=None, provenance=""):
        super(Medication, self).__init__()
        self._original_string = None
        self._normalized_string = None
        if original_string is not None:
            self.from_text(original_string)
        self._provenance = provenance
        self._seq_id=_sequential_id.next()
    def from_text(self, med_line):
        self._original_string = med_line.strip()
        self._normalized_string = self._normalize_string()
    def _normalize_string(self):
        return self._normalize_field(self._original_string)
    def _normalize_field(self, field):
        my_field = field.upper().strip()
        # Remove undesirable trailing and leading punctuation
        for punct in UNDESIRABLE_PUNCTUATION:
            my_field = my_field.strip(punct)
        my_field = ' '.join(my_field.split())
        # Normalize spacing to only one space between components
        return my_field
    @property
    def original_string(self):
        "The original unparsed string for the medication"
        return self._original_string
    @property
    def normalized_string(self):
        "The original string, normalized using _normalize_string()"
        return self._normalized_string
    def is_empty(self):
        return self.normalized_string.strip() == ""
    @property
    def provenance(self):
        "The medication's provenance"
        return self._provenance
        
def build_regular_expressions(list_of_tuples, formulation):
    my_regexps = []
    for k, v in list_of_tuples:
        new_k = k[:].replace('%FORM%', formulation)
        my_regexps.append((new_k, v))
    return my_regexps

class ParsedMedication(Medication):
    formulation_regexp_cache = {}
    times_regexp_cache = {}
    def __init__(self, med_line=None, context=None, provenance=""):
        """ParsedMedication constructor. If passed a line of text in the 
        med_line parameter, it will attempt parsing it using the from_text() 
        method. Otherwise, it will create an empty ParsedMedication. Pass
        a MappingContext as part of the context parameter to provide 
        a version of rxnorm to perform computations.""" 
        super(ParsedMedication, self).__init__(med_line, provenance)
        self._name = None
        self._dose = None
        self._units = None
        self._formulation = None
        self._instructions = None
        self._parsed = False
        self._generic_formula = None
        self._norm_dose = None
        self._cuis = None
        self._context = context
        if med_line is not None:
            self.from_text(med_line)
    def from_text(self, med_line):
        """Separates a medication string into its components according to the
        medication_parser regular expression."""
        super(ParsedMedication, self).from_text(med_line)
        med = medication_parser.findall(self.normalized_string)
        if len(med) > 0:
            med = med[0]
            self._name = self._normalize_field(med[0])
            self._dose = self._normalize_field(med[1])
            self._units = self._normalize_field(med[2])
            self._formulation = self._normalize_field(med[3])
            self._instructions = self._normalize_field(med[4])
            self._parsed = True
        else:
            logging.debug("Could not parse %s. _parsed is %r", med_line,
                          self._parsed)
    def __repr__(self):
        if self._parsed:
            return "<Medication %d @ 0x%x: %r %s %r %r (%r)>" % (
                self._seq_id,
                id(self),
                self.name,
                self.dose,
                self.units,
                self.formulation,
                self.instructions)
        else:
            return "<Medication (not parsed) %d @ 0x%x: %s>" % (
                self._seq_id,
                id(self),
                self.normalized_string)
    def __str__(self):
        if self._parsed:
            return "%s %s %s %s: %s" % (
                self.name,
                self.dose,
                self.units,
                self.formulation,
                self.instructions)
        else:
            return "%s" % self.normalized_string
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self, value):
        self._name = self._normalize_field(value)
    @property
    def dose(self):
        return self._dose
    @dose.setter
    def dose(self, value):
        self._dose = self._normalize_field(value)
    @property
    def units(self):
        return self._units
    @units.setter
    def units(self, value):
        self._units = self._normalize_field(value)
    @property
    def formulation(self):
        return copy.copy(self._formulation)
    @formulation.setter
    def formulation(self, value):
        self._formulation = self._normalize_field(value)
    @property
    def instructions(self):
        return copy.copy(self._instructions)
    @instructions.setter
    def instructions(self, value):
        self._instructions = self._normalize_field(value)
    @property
    def original_line(self):
        return self._original_string
    @property
    def parsed(self):
        return self._parsed
    @property 
    def generic_formula(self):
        if self._generic_formula is None:
            if self._context is None:
                raise MappingContextError, "Can't compute generic formula without a MappingContext object."
            self.compute_generics()
        return copy.copy(self._generic_formula)
    def as_dictionary(self):
        return {'medicationName': str(self.name),
                'dose': str(self.dose),
                'units': str(self.units),
                'formulation': str(self.formulation),
                'instructions': str(self.instructions),
                'original_string': self.original_string,
                'provenance': self.provenance,
                'normalized_dose': self._norm_dose,
                'id': self._seq_id,
                'parsed': self._parsed,
               }
    def _normalize_drug_name(self, drug_name):
        truncated = drug_name.split('@')[0].strip().upper()
        components = truncated.split()
        final_version = []
        # Replace abbreviations
        for x in components:
            if x in abbreviations:
                final_version.append(abbreviations[x])
            else:
                final_version.append(x)
        return ' '.join(final_version)
    @property
    def mappings(self):
        return self._context
    @mappings.setter
    def mappings(self, mappings):
        self._context = mappings
    def compute_generics(self, mappings=None):
        """Computes the generic equivalent of a drug according to RXNorm."""
        if mappings is None:
            mappings=self._context
        if mappings is None:
            raise MappingContextError, "Method requires a MappingContext object."
        concepts = self.CUIs(mappings)
        if concepts is not None:
            logging.debug("Concepts for %s=%r", self.name, concepts)
            try:
                concept = concepts.pop()
                ingredients = mappings.rxnorm.formulas[concept]
                self._generic_formula = [self._normalize_drug_name(x.name)
                                       for x in ingredients]
                return 
            except KeyError:
                logging.debug("Couldn't find ingredients for %s", concept)
        else:
            logging.debug("Couldn't find %s in RXNorm" % self.name)
        self._generic_formula = [self._normalize_drug_name(self.name)]
        return 
    def CUIs(self, mappings=None):
        if mappings is None:
            mappings=self._context
        if mappings is None:
            raise MappingContextError, "Method requires a MappingContext object."
        if self._cuis is None:
            if self.name is not None:
                name_of_medication = self.name.lower()
                if name_of_medication in mappings.concept_names:
                    concepts = copy.copy(mappings.concept_names[name_of_medication])
                    self._cuis = concepts
        return copy.copy(self._cuis)
    def tradenames(self, mappings=None):
        if mappings is None:
            mappings=self._context
        my_cuis = self.CUIs(mappings)
        if my_cuis is None:
            return []
        return  reduce(operator.add, [[x._concept2.CUI 
                                       for x in mappings.rxnorm.relations 
                                       if x.relation == 'tradename_of'
                                          and x._concept1.CUI == y] 
                                      for y in my_cuis])
    def normalize_dose(self):
        """Takes a drug tuple (i.e. the output of the regular expression listed 
        above) and returns the total number of units a day the patient is 
        receiving"""
        # Assume that (if not mentioned) there is 
        # one tablet/capsule/whatever per unit of time
        number_of_units = None
        form = self.formulation
        # Make sure that we have a formulation we know about! Replace formulations 
        # with standard names.
        for known_formulation in physical_forms:
            if known_formulation in form:
                form = known_formulation
                continue
        logging.debug("The form of %r is %s.", self, form)
        if form in ParsedMedication.formulation_regexp_cache:
            regexps = ParsedMedication.formulation_regexp_cache[form]
        else:
            # Keep a cache of the regular expressions we build; doing so is
            # much faster than building them for each and every medication 
            regexps = build_regular_expressions(known_number_of_doses, form)
            logging.debug("Regexps for form %s=%r", form, regexps)
            ParsedMedication.formulation_regexp_cache[form] = regexps
        for regexp, num in regexps:
            if num == -1:
                result = re.findall(regexp, self.instructions)
                if len(result) > 0:
                    number_of_units = int(result[0])
                    continue
            else:
                if regexp in self.instructions:
                    number_of_units = num
                    continue
        if number_of_units is None:
            logging.debug("Failed matching number of units on %r; assuming 1", self)
            number_of_units = 1
        if form in ParsedMedication.times_regexp_cache:
            regexps = ParsedMedication.times_regexp_cache[form]
        else:
            regexps = build_regular_expressions(known_times_per_day, form)
            ParsedMedication.times_regexp_cache[form] = regexps
        times_per_day = None
        for regexp, times in regexps:
            if times == -1:
                # Regular expression to be parsed
                result = re.findall(regexp, self.instructions)
                if len(result) > 0:
                    times_per_day = int(result[0])
                    continue
            else:
                if regexp in self.instructions:
                    times_per_day = times
                    continue
        if times_per_day is None:
            logging.debug("Failed matching times per day on %r. Assuming 1.", self)
            times_per_day = 1
        # else:
            #print drug_tuple, "is taken %d times a day" % times_per_day
        #logging.debug("The total quantity of %r is %1.2f %s a day", 
        #    self.name, self.dose*times_per_day*number_of_units, self.units)
        try:
            self._norm_dose = '%s %s*%d*%d' % (
                str(self.dose), self.units, times_per_day, number_of_units)
        except ValueError:
            return
        logging.debug("The normalized dose for %s is %s", self,
                      self._norm_dose)
    @property
    def normalized_dose(self):
        if self._norm_dose is None:
            self.normalize_dose()
        return copy.copy(self._norm_dose)
    def fieldwise_comparison(self, other):
        """Compares two medication objects field by field, based on the 
        contents of the MEDICATION_FIELDS constant. Returns a set containing
        the identical fields."""
        result=set()
        for field in MEDICATION_FIELDS.keys():
            if self.__getattribute__(field)==other.__getattribute__(field):
                result.add(MEDICATION_FIELDS[field])
        return list(result)
    
        
