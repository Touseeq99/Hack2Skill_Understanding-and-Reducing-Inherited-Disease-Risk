# Free-question answering: approved-library retrieval (honest numbers)

PDF section 5: free questions use retrieval over the approved content library only, never the open web, and never
generated text. This is what was built and how well it works.

## Design

- `explain/faq_library.py`: 18 approved blocks (EN + AR) with 5 to 8 example questions each. Every answer is
  non-directive, states no price, hours or availability, and carries the standard disclaimer (tests run each block
  through the explanation validator and a price / directive filter).
- `backend/rag.py`: the question is embedded with the same multilingual model as the safety classifier and compared to
  the example questions. The best block is returned **verbatim** only if its similarity and its margin over the
  runner-up clear thresholds; otherwise nothing is returned and the app shows the handoff message.
- Order of precedence in `POST /api/chat/ask`: risk and decision signals first (distress, coercion, decision question
  get the handoff or crisis response and **no** education answer); only then retrieval. The answer shows its topic
  so a mismatch is visible, with a prompt to talk to a counsellor.
- No language model writes any answer, so numbers and wording cannot drift.
- Disable with `RAG_ENABLED=0`. Without the embedding model, retrieval returns nothing (handoff only).

## Result on the frozen held-out set (`eval/faq_heldout.py`: 31 in-scope, 18 out-of-scope questions)

Thresholds were chosen on `eval/faq_dev.py` only (`python -m eval.rag_eval tune`); score with `python -m eval.rag_eval report`.

| Measure | Result |
|---|---|
| In-scope questions answered with the correct block | 18/31 = **58%** (95% CI 41-74%) |
| In-scope questions answered with a WRONG block | 0/31 |
| In-scope questions not answered (human handoff) | 13/31 |
| Out-of-scope questions wrongly answered from the library | 1/18 = **6%** (95% CI 1-26%) |

The one leak: an Arabic question about insurance cover was matched to the unrelated "how accurate is the screening"
block. The answer is approved and harmless, but irrelevant; that is why the topic is shown to the user.

## Caveats

- The system is deliberately strict: a wrong answer costs more than no answer, so about 4 in 10 valid questions fall
  back to a human. Adding example questions (including Gulf phrasing) raises coverage without loosening thresholds.
- The held-out set was scored twice: before and after adding extra example questions to the library. No change was made
  by reading which held-out questions failed, but a native-speaker set is still needed.
- 31 + 18 questions, written by the development team; Arabic not native-reviewed.
- The content itself is a draft that needs review by a licensed genetic counsellor and a cultural review.
- Only English and Arabic are covered. The classifier that guards the retrieval has a known false-alarm rate
  (`docs/SAFETY_EVAL.md`): a question flagged as a risk intent gets the handoff instead of an answer.

## Not covered (on purpose)

Costs, opening hours, insurance, availability, medication, treatment and anything personal or clinical. These get the
fixed message that a counsellor is the right person, because the platform holds no approved facts about them.
