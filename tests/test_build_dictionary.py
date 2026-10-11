"""Choosing Wiktionary pronunciations and senses from kaikki.org records."""
import build_dictionary as build


def record(word, pos, sounds=(), senses=({"glosses": ["A meaning."]},)):
    return {"word": word, "pos": pos, "sounds": list(sounds), "senses": list(senses)}


def test_british_ipa_is_the_first_whole_standard_british_transcription_in_oxford_notation():
    sounds = [{"ipa": "/ˈkɑɹnəl/", "tags": ["General-American"]},
              {"ipa": "/ˈzʊɡ.-/", "tags": ["UK"]},
              {"ipa": "[ˈbɹʷɪtʰəl]", "tags": ["UK"]},
              {"ipa": "/ˈɔːld/", "tags": ["UK", "obsolete"]},
              {"ipa": "/əˈbɹɪd͡ʒ.aɪ̯/", "tags": ["Received-Pronunciation"]}]
    assert build.british_ipa(record("x", "verb", sounds)) == "/əˈbrɪdʒaɪ/"


def test_untagged_transcriptions_are_not_taken_as_british():
    assert build.british_ipa(record("alleviate", "verb", [{"ipa": "/əˈli.vi.eɪt/"}])) is None


def test_groups_keep_each_pronunciation_with_its_own_senses():
    records = [record("buffet", "noun", [{"ipa": "/ˈbʊfeɪ/", "tags": ["UK"]}], [{"glosses": ["A sideboard."]}]),
               record("buffet", "noun", [], [{"glosses": ["A blow."]}]),
               record("buffet", "verb", [], [{"glosses": ["To strike."]}, {"glosses": ["To gut."], "tags": ["obsolete"]}])]
    assert build.groups(records) == [{"ipa": "/ˈbʊfeɪ/", "senses": ["(noun) A sideboard."]},
                                     {"ipa": "", "senses": ["(noun) A blow.", "(verb) To strike."]}]


def test_groups_show_labels_and_stop_at_the_limit():
    senses = [{"glosses": [f"Sense {n}."], "raw_glosses": [f"(rare) Sense {n}."]} for n in range(12)]
    lines = build.groups([record("x", "noun", senses=senses)])[0]["senses"]
    assert len(lines) == build.MAX_SENSES and lines[0] == "(noun) (rare) Sense 0."


def test_exact_spelling_wins_over_other_capitalisations():
    month, majestic = record("August", "name"), record("august", "adj")
    assert build.matching("august", [month, majestic]) == [majestic]
    assert build.matching("Scrooge", [record("scrooge", "noun")])[0]["word"] == "scrooge"


def alternative(word, *targets):
    """Return a record with one alternative-of sense per target."""
    return record(word, "noun", senses=[{"glosses": ["Alternative spelling."], "alt_of": [{"word": t}]}
                                        for t in targets])


def test_a_variant_takes_an_equal_share_of_each_main_spelling():
    gibe = alternative("gibe", "gybe", "jibe")
    targets = {"gybe": [record("gybe", "verb", senses=[{"glosses": [f"Sail {n}."]} for n in range(8)])],
               "jibe": [record("jibe", "noun", senses=[{"glosses": ["A taunt."]}])]}
    senses = build.lookup_entry([gibe], targets)[0]["senses"]
    assert "(noun) A taunt." in senses and len(senses) == build.MAX_SENSES // 2 + 1


def test_a_link_split_at_a_comma_is_not_followed():
    split = record("close but no cigar", "phrase",
                   senses=[{"glosses": ["Alternative form."], "alt_of": [{"word": "close"}, {"word": "but no cigar"}]}])
    assert build.main_spellings([split]) == []
    assert build.main_spellings([alternative("valor", "valour")]) == ["valour"]


def test_an_entry_with_senses_of_its_own_is_not_a_variant():
    assert build.main_spellings([alternative("x", "y"), record("x", "verb")]) == []


def test_only_pronunciations_are_kept_and_senses_only_to_choose_between_several():
    one = [{"ipa": "/əˈbeɪt/", "senses": ["(verb) To lessen."]}]
    several = [{"ipa": "/ˈbʊfeɪ/", "senses": ["(noun) A sideboard."]}, {"ipa": "", "senses": ["(verb) To strike."]}]
    assert build.needed(one) == [{"ipa": "/əˈbeɪt/", "senses": []}]
    assert build.needed(several) == several
    assert build.needed([{"ipa": "", "senses": ["(noun) Origin."]}]) == []
