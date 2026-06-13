# 2026 FIFA World Cup: bracket and allocation notes

Generated 2026-06-12 (AEST). Companion to `data/fixtures.json`. Sources and verification status are listed at the end.

## 1. Third-placed teams in the Round of 32

48 teams, 12 groups of 4. The top two in every group advance, together with the 8 best third-placed teams, for 32 in the knockout phase.

Eight Round of 32 slots take a third-placed team. Each slot lists the groups whose third may be assigned to it (candidate pools as published in the official schedule):

- Match 74: Winner Group E v third place from A/B/C/D/F
- Match 77: Winner Group I v third place from C/D/F/G/H
- Match 79: Winner Group A v third place from C/E/F/H/I
- Match 80: Winner Group L v third place from E/H/I/J/K
- Match 81: Winner Group D v third place from B/E/F/I/J
- Match 82: Winner Group G v third place from A/E/H/I/J
- Match 85: Winner Group B v third place from E/F/G/I/J
- Match 87: Winner Group K v third place from D/E/I/J/L

Allocation rules:
1. Only the 8 best-ranked thirds (section 3) enter the bracket.
2. A third-placed team is never assigned to the slot of its own group winner (no pool contains the host group's own letter).
3. For the actual combination of the 8 qualified groups, the assignment follows the combination table annexed to the FIFA competition regulations, which maps each possible set of qualified thirds to a unique slot assignment consistent with the pools above. A simulator should implement this as a constraint-satisfaction step: assign the 8 qualified thirds to the 8 slots such that every slot receives a third from its candidate pool, with the published table as the tie-break among multiple feasible assignments.
4. Verify the exact combination table against the FIFA regulations before relying on simulated third-place routing; the candidate pools above were captured from the official schedule as rendered on the Wikipedia article, and the full table was not re-checked in this session (see section 6).

## 2. Group-stage tiebreakers (in order)

1. Points in all group matches.
2. Goal difference in all group matches.
3. Goals scored in all group matches.
4. Points in matches among the teams still tied.
5. Goal difference in matches among the teams still tied.
6. Goals scored in matches among the teams still tied.
7. Fair play points (yellow card minus 1, indirect red minus 3, direct red minus 4, yellow then direct red minus 5).
8. Drawing of lots.

## 3. Ranking the third-placed teams (best 8 of 12)

1. Points.
2. Goal difference.
3. Goals scored.
4. Fair play points (scale as above).
5. Drawing of lots.

Head-to-head criteria do not apply across groups.

## 4. Knockout bracket: feed map

Round of 32 (match, date, venue city, pairing):
- 73: Jun 28, Inglewood: Runner-up A v Runner-up B
- 74: Jun 29, Foxborough: Winner E v Third A/B/C/D/F
- 75: Jun 29, Guadalupe (Monterrey): Winner F v Runner-up C
- 76: Jun 29, Houston: Winner C v Runner-up F
- 77: Jun 30, East Rutherford: Winner I v Third C/D/F/G/H
- 78: Jun 30, Arlington (Dallas): Runner-up E v Runner-up I
- 79: Jun 30, Mexico City: Winner A v Third C/E/F/H/I
- 80: Jul 1, Atlanta: Winner L v Third E/H/I/J/K
- 81: Jul 1, Santa Clara (San Francisco Bay Area): Winner D v Third B/E/F/I/J
- 82: Jul 1, Seattle: Winner G v Third A/E/H/I/J
- 83: Jul 2, Toronto: Runner-up K v Runner-up L
- 84: Jul 2, Inglewood (Los Angeles): Winner H v Runner-up J
- 85: Jul 2, Vancouver: Winner B v Third E/F/G/I/J
- 86: Jul 3, Miami Gardens: Winner J v Runner-up H
- 87: Jul 3, Kansas City: Winner K v Third D/E/I/J/L
- 88: Jul 3, Arlington: Runner-up D v Runner-up G

Round of 16:
- 89: Jul 4, Philadelphia: Winner Match 74 v Winner Match 77
- 90: Jul 4, Houston: Winner Match 73 v Winner Match 75
- 91: Jul 5, East Rutherford: Winner Match 76 v Winner Match 78
- 92: Jul 5, Mexico City: Winner Match 79 v Winner Match 80
- 93: Jul 6, Arlington: Winner Match 83 v Winner Match 84
- 94: Jul 6, Seattle: Winner Match 81 v Winner Match 82
- 95: Jul 7, Atlanta: Winner Match 86 v Winner Match 88
- 96: Jul 7, Vancouver: Winner Match 85 v Winner Match 87

Quarter-finals:
- 97: Jul 9, Foxborough (Boston): Winner Match 89 v Winner Match 90
- 98: Jul 10, Inglewood: Winner Match 93 v Winner Match 94
- 99: Jul 11, Miami Gardens: Winner Match 91 v Winner Match 92
- 100: Jul 11, Kansas City: Winner Match 95 v Winner Match 96

Semi-finals, third place and final:
- 101: Jul 14, Arlington: Winner Match 97 v Winner Match 98
- 102: Jul 15, Atlanta: Winner Match 99 v Winner Match 100
- 103: Jul 18, Miami Gardens: Loser Match 101 v Loser Match 102
- 104: Jul 19, East Rutherford: Winner Match 101 v Winner Match 102

Structural checks (all pass in `fixtures.json`): each group winner and each runner-up appears exactly once across matches 73 to 88; exactly 8 third-place slots; winners of 73 to 96 each feed exactly one later match; semi-final losers meet in match 103.

## 5. Matches played as of 2026-06-12 (AEST)

- Match 1 (Group A, 11 June, Estadio Azteca, Mexico City): Mexico 2-0 South Africa.
- Match 2 (Group A, 11 June, Estadio Akron, Zapopan): South Korea 2-1 Czech Republic.

Matches 3 (Canada v Bosnia and Herzegovina, Toronto) and 4 (United States v Paraguay, Inglewood) are scheduled for the evening of 12 June local time and had not kicked off at generation time.

## 6. Sources and verification status

Accessed this session:
- https://raw.githubusercontent.com/martj42/international_results/master/results.csv (historical dataset; canonical team naming; all 72 group fixtures cross-checked 1:1 against it; March 2026 playoff results)
- https://en.wikipedia.org/wiki/2026_FIFA_World_Cup (parsed by the project pipeline `fetch_results.py`, which built the fixture state, official match numbers, venues, bracket placeholders and the two played scores)

Referenced, not directly fetched this session (general web access was not permitted; verify on next refresh):
- https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_group_stage
- https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage
- https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_qualification
- FIFA competition regulations (digitalhub.fifa.com), for the tiebreaker text and the third-place combination table

Confidence notes:
- Teams, groups, group letters and all 72 group fixtures are corroborated by two independent structures (the dataset fixture rows and the parsed schedule) and are internally consistent (perfect round robins, host anchoring).
- Official match numbers, knockout venues and dates, candidate pools and bracket feeds come from the parsed official schedule on the Wikipedia article; they are internally consistent and match host-path constraints, but rest on that single parse.
- The two played scores appear in the parsed article and in `data/live_results.csv`; both trace to the same parse, so they were not independently confirmed against a second outlet in this session.
- The exact tiebreaker and third-ranking wording follows the published FIFA regulations as known at generation; re-check both lists against the regulations PDF before simulating tie edge cases.
- Manual corrections belong in `data/adjustments.json`, which the project reserves for that purpose.
