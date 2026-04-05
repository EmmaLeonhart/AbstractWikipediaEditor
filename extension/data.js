// Function registry and aliases for the wikitext parser
// Ported from data/function_aliases.json and wikitext_parser.py FUNCTION_REGISTRY

const FUNCTION_ALIASES = {
  "location": "Z26570", "located in": "Z26570",
  "is a": "Z26039", "instance of": "Z26039",
  "kind of": "Z26095", "subclass of": "Z26095",
  "role": "Z28016", "is the x of": "Z28016",
  "describe": "Z29591", "adjective class": "Z29591",
  "class of class": "Z27173",
  "class with adj": "Z29743",
  "superlative": "Z27243",
  "spo": "Z26955",
  "are": "Z26627", "plural class": "Z26627",
  "album": "Z28803",
  "sunset": "Z30000",
  "begins": "Z31405",
  "auto article": "Z29822",
  "to html": "Z27868",
  "text to html": "Z29749",
  "string of": "Z14396",
};

const FUNCTION_REGISTRY = {
  "Z26570": {
    name: "State location using entity and class",
    params: [
      { key: "K1", name: "entity", type: "entity_ref" },
      { key: "K2", name: "class", type: "Q-item" },
      { key: "K3", name: "location", type: "Q-item" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z28016": {
    name: "defining role sentence",
    params: [
      { key: "K1", name: "subject", type: "Q-item" },
      { key: "K2", name: "role", type: "Q-item" },
      { key: "K3", name: "dependency", type: "entity_ref" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z26039": {
    name: "Article-less instantiating fragment",
    params: [
      { key: "K1", name: "entity", type: "entity_ref" },
      { key: "K2", name: "class", type: "Q-item" },
      { key: "K3", name: "language", type: "language" },
    ],
    returns: "Z6",
  },
  "Z26095": {
    name: "Article-ful instantiating fragment",
    params: [
      { key: "K1", name: "class", type: "Q-item" },
      { key: "K2", name: "super-class", type: "Q-item" },
      { key: "K3", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z26955": {
    name: "SPO sentence",
    params: [
      { key: "K1", name: "predicate", type: "Q-item" },
      { key: "K2", name: "subject_item", type: "Q-item" },
      { key: "K3", name: "object_item", type: "Q-item" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z6",
  },
  "Z29591": {
    name: "describing entity with adjective / class",
    params: [
      { key: "K1", name: "entity", type: "entity_ref" },
      { key: "K2", name: "adjective", type: "Q-item" },
      { key: "K3", name: "class", type: "Q-item" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z27173": {
    name: "Describe the class of a class",
    params: [
      { key: "K1", name: "class_described", type: "Q-item" },
      { key: "K2", name: "adjective", type: "Q-item" },
      { key: "K3", name: "class_describing", type: "Q-item" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z6",
  },
  "Z29743": {
    name: "description of class with adjective and superclass",
    params: [
      { key: "K1", name: "described_class", type: "Q-item" },
      { key: "K2", name: "adjective", type: "Q-item" },
      { key: "K3", name: "superclass", type: "Q-item" },
      { key: "K4", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z27243": {
    name: "Superlative definition",
    params: [
      { key: "K1", name: "entity", type: "entity_ref" },
      { key: "K2", name: "adjective", type: "Q-item" },
      { key: "K3", name: "class", type: "Q-item" },
      { key: "K4", name: "location", type: "Q-item" },
      { key: "K5", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z26627": {
    name: "Classifying a class of nouns",
    params: [
      { key: "K1", name: "class", type: "Q-item" },
      { key: "K2", name: "class2", type: "Q-item" },
      { key: "K3", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z28803": {
    name: "short description for album",
    params: [
      { key: "K1", name: "album", type: "Q-item" },
      { key: "K2", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z31405": {
    name: "Sentence that something begins",
    params: [
      { key: "K1", name: "subject", type: "Q-item" },
      { key: "K2", name: "language", type: "language" },
    ],
    returns: "Z11",
  },
  "Z29822": {
    name: "ArticlePlaceholder render article",
    params: [
      { key: "K1", name: "display_language", type: "language" },
      { key: "K2", name: "item", type: "Q-item" },
      { key: "K3", name: "include_empty", type: "boolean" },
    ],
    returns: "Z89",
  },
};

// Property-to-function mapping (synced with data/property_function_mapping.json)
const PROPERTY_MAPPING = {
  "P31":   { function: "Z26039", template: "{{Z26039 | $subject | $value}}", skip_if: ["P106"] },
  "P279":  { function: "Z26095", template: "{{Z26095 | $subject | $value}}" },
  "P131":  { function: "Z26570", template: "{{Z26570 | $subject | $P31_value | $value}}", location_priority: 1 },
  "P17":   { function: "Z26570", template: "{{Z26570 | $subject | $P31_value | $value}}", location_priority: 2 },
  "P30":   { function: "Z26570", template: "{{Z26570 | $subject | $P31_value | $value}}", location_priority: 3 },
  "P36":   { function: "Z28016", template: "{{Z28016 | $value | Q5119 | $subject}}" },
  "P6":    { function: "Z28016", template: "{{Z28016 | $value | Q2285706 | $subject}}" },
  "P35":   { function: "Z28016", template: "{{Z28016 | $value | Q48352 | $subject}}" },
  "P825":  { function: "Z26955", template: "{{Z26955 | Q1762010 | $subject | $value}}" },
  "P138":  { function: "Z26955", template: "{{Z26955 | Q2607563 | $subject | $value}}" },
  "P361":  { function: "Z26955", template: "{{Z26955 | Q66305721 | $subject | $value}}" },
  "P106":  { function: "Z26039", template: "{{Z26039 | $subject | $value}}" },
  "P27":   { function: "Z26955", template: "{{Z26955 | Q42138 | $subject | $value}}" },
  "P495":  { function: "Z26955", template: "{{Z26955 | Q3373417 | $subject | $value}}" },
  "P1376": { function: "Z28016", template: "{{Z28016 | $subject | Q5119 | $value}}", skip_if: ["P36"] },
  "P37":   { function: "Z26955", template: "{{Z26955 | Q23492 | $value | $subject}}" },
  "P38":   { function: "Z26955", template: "{{Z26955 | Q8142 | $value | $subject}}" },
};

// Only the most specific location property is used (P131 > P17 > P30)
const LOCATION_PROPS = new Set(["P131", "P17", "P30"]);
