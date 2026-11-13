| Случай | Что проверяет | v2 | v3 | aggressive |
|---|---|---|---|---|
| E11-01 | formulation, optional_dilution | нет: order:base-plus>other<br>other 1 / base-plus 2<br>clarify | да<br>base-plus 1 / other 2<br>review_top · stable | да<br>base-plus 1 / other 2<br>review_top · stable |
| E11-02 | critical_gap, many_small_pluses, decisive_question | нет: order:core-ok>pluses<br>pluses 1 / core-ok 2<br>clarify | да<br>core-ok 1 / pluses 2<br>clarify · open | да<br>core-ok 1 / pluses 2<br>clarify · open |
| E11-03 | formulation, repeat | нет: order:repeat>mid, tie:repeat=plain<br>plain 1 / mid 2 / repeat 3<br>review_top | да<br>plain 1 / repeat 1 / mid 3<br>clarify · close | да<br>plain 1 / repeat 1 / mid 3<br>clarify · close |
| E11-04 | formulation, rename, permutation | да<br>vacancy-a 1 / zz-copy 1<br>clarify | да<br>vacancy-a 1 / zz-copy 1<br>clarify · open | да<br>vacancy-a 1 / zz-copy 1<br>clarify · open |
| E11-05 | formulation, split, known_limit | ограничение, без ожидания<br>L: {'split': 75.0, 'single': 50.0} | ограничение, без ожидания<br>L: {'split': 75.0, 'single': 50.0} | — |
| E11-06 | mandatory_source, misattributed_marker | да<br>unbound 1 / violated 2<br>clarify | да<br>unbound 1 / violated 2<br>clarify · open | да<br>unbound 1 / violated 2<br>clarify · open |
| E11-07 | unknown_vs_fail | да<br>silent 1 / denied 2<br>clarify | да<br>silent 1 / denied 2<br>clarify · open | да<br>silent 1 / denied 2<br>clarify · open |
| E11-08 | disputed_full, disputed_fail | да<br>solid 1 / disputed-fail 2 / disputed-full 2<br>clarify | да<br>solid 1 / disputed-fail 2 / disputed-full 2<br>clarify · open | да<br>solid 1 / disputed-fail 2 / disputed-full 2<br>clarify · open |
| E11-09 | weak_matches_vs_relevant_experience | нет: order:relevant>weak<br>weak 1 / relevant 2<br>clarify | да<br>relevant 1 / weak 2<br>review_top · stable | да<br>relevant 1 / weak 2<br>review_top · stable |
| E11-10 | comparability, close_results | нет: established:False<br>short 1 / long 2<br>review_top | да<br>short 1 / long 2<br>clarify · close | да<br>short 1 / long 2<br>clarify · close |
| E11-11 | comparability, clear_lead | да<br>short 1 / long 2<br>review_top | да<br>short 1 / long 2<br>review_top · stable | да<br>short 1 / long 2<br>review_top · stable |
| E11-12 | tie | да<br>a 1 / b 1<br>review_top | да<br>a 1 / b 1<br>review_top · tie | да<br>a 1 / b 1<br>review_top · tie |
| E11-13 | lower_job_can_overtake, decisive_question | нет: established:False<br>top 1 / second 2<br>review_top | да<br>top 1 / second 2<br>clarify · open | да<br>top 1 / second 2<br>clarify · open |
| E11-14 | empty_job, optimistic_upper | да<br>fit 1 / empty 2<br>review_top | да<br>fit 1 / empty 2<br>review_top · stable | нет: established:True<br>fit 1 / empty 2<br>clarify · stable |
| E11-15 | far_challenger | да<br>top 1 / far 2<br>review_top | да<br>top 1 / far 2<br>review_top · stable | нет: established:True<br>top 1 / far 2<br>clarify · stable |
| E11-16 | incomplete_run | да<br>a 1 / b 2<br>incomplete | да<br>a 1 / b 2<br>incomplete · stable | да<br>a 1 / b 2<br>incomplete · stable |
| E11-17 | cost_of_v3, marker_error | да<br>marker 1 / other 1<br>clarify | да<br>other 1 / marker 2<br>clarify · open | да<br>other 1 / marker 2<br>clarify · open |

Случаев с ожиданием: 16 из 17; пройдено — v2 10, v3 16, aggressive 14.
Исправлено v3: E11-01, E11-02, E11-03, E11-09, E11-10, E11-13.
Новые регрессии v3: нет.
Сменилось первое место: E11-01, E11-02, E11-03, E11-09, E11-17.
Сменилась рекомендация: E11-01, E11-03, E11-09, E11-10, E11-13.
Запусков с «уточнить»: v2 8, v3 9, aggressive 11; решающих строк названо v3: 11.
Aggressive хуже v3: E11-14, E11-15.
Известные ограничения: E11-05.
Локальный расчёт score + rank на один запуск: v2 62.5 мкс, v3 376.6 мкс (не latency API).
