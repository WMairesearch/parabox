import Lean
open Lean Elab

/-- Parse and elaborate one Lean file, then print command syntax ranges as JSON.
The ranges are UTF-8 byte offsets. This is the research scanner; it is not mounted
into the participant workspace. -/
def scan (path : System.FilePath) : IO Json := do
  let input ← IO.FS.readFile path
  let inputCtx := Parser.mkInputContext input path.toString
  let (header, parserState, messages) ← Parser.parseHeader inputCtx
  let (env, messages) ← processHeader header {} messages inputCtx
  let cmdState := Command.mkState env messages {}
  let st ← Elab.IO.processCommands inputCtx parserState cmdState
  let mut arr : Array Json := #[]
  for stx in st.commands do
    if stx.getKind == ``Parser.Command.eoi then
      continue
    let start := stx.getPos?.map (·.byteIdx) |>.getD 0
    let stop := stx.getTailPos?.map (·.byteIdx) |>.getD start
    arr := arr.push <| Json.mkObj [
      ("kind", Json.str stx.getKind.toString),
      ("start", Json.num start),
      ("stop", Json.num stop)
    ]
  return Json.arr arr

def main (args : List String) : IO UInt32 := do
  let path := args.headD ""
  if path.isEmpty then
    IO.eprintln "usage: Scan.lean FILE"
    return 1
  try
    IO.println (← scan path).compress
    return 0
  catch e =>
    IO.eprintln s!"SCAN_ERROR {e.toString}"
    return 1
