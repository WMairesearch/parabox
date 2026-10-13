import Lean
open Lean Meta

/-- Print, as one JSON array, the signature and docstring of each requested Mathlib
declaration. Names that the environment does not contain are skipped. This runs offline
in the research image via `lake env lean --run`; its output is frozen into a corpus file
and never reaches a participant. -/

def collect (names : Array Name) : MetaM Json := do
  let env ← getEnv
  let mut arr : Array Json := #[]
  for name in names do
    match env.find? name with
    | none => pure ()
    | some ci =>
      let fmt ← ppExpr ci.type
      let doc := (← findDocString? env name).getD ""
      arr := arr.push <| Json.mkObj [
        ("name", Json.str (toString name)),
        ("type", Json.str fmt.pretty),
        ("doc", Json.str doc)
      ]
  return Json.arr arr

def main (args : List String) : IO UInt32 := do
  let namesFile := args.getD 0 ""
  if namesFile.isEmpty then
    IO.eprintln "usage: Extract.lean NAMES_FILE"
    return 1
  let content ← IO.FS.readFile namesFile
  let names : Array Name := content.splitOn "\n" |>.toArray.filterMap fun line =>
    let s := line.trim
    if s.isEmpty then none else some s.toName
  initSearchPath (← findSysroot)
  let env ← importModules #[{ module := `Mathlib }] {}
  let coreCtx : Core.Context := { fileName := "corpus", fileMap := default }
  let coreState : Core.State := { env := env }
  let (json, _) ← ((collect names).run' {} {}).toIO coreCtx coreState
  IO.println json.compress
  return 0
