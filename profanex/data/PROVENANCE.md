# Lexicon provenance and license

## Packaged banned lexicon

`banned_words.yaml` is derived in substantial part from the English list in [LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words](https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words), © 2012–2020 Shutterstock, Inc., licensed under the [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).

Profanex modifies that source by selecting a smaller subset, removing duplicates, adding spelling and mask variants, assigning policy categories, and applying ongoing false-positive and recall review. The packaged derivative lexicon is distributed under CC BY 4.0, not the repository's MIT software license. No endorsement by Shutterstock or the upstream contributors is implied.

## Packaged allowlist

`allowlist.yaml` is a Profanex-maintained list of common false-positive magnets and is distributed under the repository's MIT license.

## Curation policy

The categories are moderation-policy aids, not statements about people or identity. Terms can belong to multiple categories when their common uses overlap. Changes to the packaged data should include:

- a true-positive or false-positive fixture demonstrating the policy decision;
- a category review for newly added terms;
- a note here when the upstream source or licensing basis changes.

Current intentional exclusions include mild `damn` / `hell`, bare `kill` / `murder`, context-neutral anatomical or adult-topic terms such as `anal`, `breasts`, `penis`, `vagina`, `escort`, and `erotic`, and ambiguous homographs such as `asses`, `balls`, `bareback`, `big black`, `boner`, `butt`, `cum`, `dick`, `dike`, `dyke`, and `dogging`. Applications that moderate those terms can add them through `extra_banned`. Packaged `general` entries are kept separate from the more specific `sexual`, `excretory`, `slurs`, and `violence` categories so category exclusion is predictable. Custom lexicons may intentionally assign multiple categories to one term. The packaged allowlist covers common substring magnets such as `classic`, `password`, and `assassin`.

## Review record

| Date       | Scope |
| ---------- | ----- |
| 2026-08-12 | Removed ambiguous whole-word homographs from defaults, made packaged categories exclusive, and gave allowlist entries final precedence. |
| 2026-08-12 | Reduced default false positives from numeric-only leet tokens and context-neutral anatomical/adult-topic terms. |
| 2026-08-11 | Corrected upstream attribution and CC BY 4.0 licensing; removed duplicate data; audited clear sexual, slur, and excretory category tags. |
