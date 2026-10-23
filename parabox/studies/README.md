# Historical studies

These are the exploratory experiments that preceded the two installed Parabox
benchmarks. They are available in a source checkout, not in the wheel or source
distribution. Start with [the current experiment designs](../../docs/experiments.md)
if you want to run the released benchmark. Historical schedules, tasks, scoring,
and model configurations differ; do not pool their rates with new runs.

## How the experiments developed

| Question | Study code | What changed |
|---|---|---|
| Can a method travel between agents? | [`relay/`](relay/), [`relay_board/`](relay_board/), [`relay_files/`](relay_files/), [`relay_search/`](relay_search/) | Compared isolated work with static or agent-updated libraries, message boards, files, and search delivery. |
| Will agents find, use, or publish peer advice? | [`discovery/`](discovery/), [`discovery_code/`](discovery_code/), [`write/`](write/), [`write_code/`](write_code/) | Separated finding a note from acting on it, and acting from writing advice for a later agent. |
| Does task and verifier design change method adoption? | [`mechspan_code/`](mechspan_code/), [`composition/`](composition/), [`unified/`](unified/), [`spillover/`](spillover/) | Varied code tasks, verifier acceptance paths, task solvability, feedback, and peer-note content. The unified study covered independent, chain, and population schedules. |
| Does a method persist, or can a later agent interrupt it? | [`transmission/`](transmission/), [`transmission_door/`](transmission_door/), [`board/`](board/), [`population/`](population/), [`continuation/`](continuation/) | Followed successive agents and shared records; some designs introduced warnings, record selection, or changes at a generation boundary. |
| What happens when agents maintain shared task infrastructure? | [`shared_wiki/`](shared_wiki/), [`costly_information/`](costly_information/) | The former tracked private-test access and wiki contributions across recipient chains. The latter tested scored short submissions that disclose a hidden ternary value to successors. |

The studies motivated the current separation of publication, delivery, exposure,
adoption, and continuation. A shared file is not evidence that anyone read it;
a verifier-accepted program is not necessarily a correct program; and a zero-point
information submission is not by itself evidence of successor benefit.

## Evidence and scope

Earlier summary tables are in [`report/final/`](../../report/final/),
[`report/longchain/`](../../report/longchain/),
[`report/composition/`](../../report/composition/),
[`report/mechspan/`](../../report/mechspan/), and
[`report/population/`](../../report/population/). The shared-test-wiki analyses
are in [`report/shared-test-wiki/`](../../report/shared-test-wiki/); resource
measurements are in [`report/resource-allocation/`](../../report/resource-allocation/).
These are retained historical summaries, not results of the installed benchmark.
The [current results page](../../report/results.md) states what has been released
for the integrated protocols.

Study code depends on the common task and execution modules, never the other
way around. Only a limited [study smoke suite](tests/test_smoke.py) is maintained
here. Reproducing a historical comparison requires its original specification,
model configuration, image, and run artifacts; the published CSVs alone are not
a full replay bundle. Do not start paid model sessions while exploring this code.
