import Lean

/-!
Decode the complete *stored* structural Expr exported by TermIdentity.lean.
This file deliberately does not import KernelTrial or elaborate the source proof.
It asks Lean's kernel to infer the reconstructed term's type and compare it to
the separately decoded claimed theorem type. Unsupported constructors reject.
-/

open Lean Elab Command

private def field (j : Json) (k : String) : Except String Json :=
  j.getObjVal? k

private def textField (j : Json) (k : String) : Except String String := do
  let value ← field j k
  value.getStr?

private def natField (j : Json) (k : String) : Except String Nat := do
  let value ← field j k
  value.getNat?

private def boolField (j : Json) (k : String) : Except String Bool := do
  let value ← field j k
  value.getBool?

private partial def decodeName (j : Json) : Except String Name := do
  match ← textField j "kind" with
  | "anonymous" => pure Name.anonymous
  | "str" => do
      let parent ← decodeName (← field j "prefix")
      let value ← textField j "value"
      pure (Name.str parent value)
  | "num" => do
      let parent ← decodeName (← field j "prefix")
      let value ← natField j "value"
      pure (Name.num parent value)
  | other => .error s!"unsupported serialized Name constructor: {other}"

private partial def decodeLevel (j : Json) : Except String Level := do
  match ← textField j "kind" with
  | "zero" => pure Level.zero
  | "succ" => do
      let value ← decodeLevel (← field j "of")
      pure (Level.succ value)
  | "max" => do
      let left ← decodeLevel (← field j "left")
      let right ← decodeLevel (← field j "right")
      pure (Level.max left right)
  | "imax" => do
      let left ← decodeLevel (← field j "left")
      let right ← decodeLevel (← field j "right")
      pure (Level.imax left right)
  | "param" => do
      let name ← decodeName (← field j "name")
      pure (Level.param name)
  | other => .error s!"unsupported serialized Level constructor: {other}"

private def decodeBinderInfo (name : String) : Except String BinderInfo :=
  match name with
  | "default" => pure BinderInfo.default
  | "implicit" => pure BinderInfo.implicit
  | "strictImplicit" => pure BinderInfo.strictImplicit
  | "instImplicit" => pure BinderInfo.instImplicit
  | _ => .error "unsupported binder annotation"

private partial def decodeExpr (j : Json) : Except String Expr := do
  match ← textField j "kind" with
  | "bvar" => pure <| Expr.bvar (← natField j "index")
  | "sort" => pure <| Expr.sort (← decodeLevel (← field j "level"))
  | "const" => do
      let name ← decodeName (← field j "name")
      let levelsJson ← (← field j "levels").getArr?
      let levels ← levelsJson.toList.mapM decodeLevel
      pure <| Expr.const name levels
  | "app" => do
      let fn ← decodeExpr (← field j "fn")
      let arg ← decodeExpr (← field j "arg")
      pure <| Expr.app fn arg
  | "lam" => do
      let domain ← decodeExpr (← field j "domain")
      let body ← decodeExpr (← field j "body")
      let info ← decodeBinderInfo (← textField j "binderInfo")
      pure <| Expr.lam Name.anonymous domain body info
  | "forallE" => do
      let domain ← decodeExpr (← field j "domain")
      let body ← decodeExpr (← field j "body")
      let info ← decodeBinderInfo (← textField j "binderInfo")
      pure <| Expr.forallE Name.anonymous domain body info
  | "letE" => do
      let domain ← decodeExpr (← field j "type")
      let value ← decodeExpr (← field j "value")
      let body ← decodeExpr (← field j "body")
      let nondep ← boolField j "nondep"
      pure <| Expr.letE Name.anonymous domain value body nondep
  | "natVal" => pure <| Expr.lit (.natVal (← natField j "value"))
  | "strVal" => pure <| Expr.lit (.strVal (← textField j "value"))
  | "proj" => do
      let name ← decodeName (← field j "typeName")
      let index ← natField j "index"
      let target ← decodeExpr (← field j "structure")
      pure <| Expr.proj name index target
  | other => .error s!"untrusted or unsupported serialized Expr constructor: {other}"

run_cmd do
  let raw ← liftIO <| IO.FS.readFile "term-identity.json"
  let document ← match Json.parse raw with
    | .ok doc => pure doc
    | .error _ => throwError "kernel recheck: invalid serialized JSON"
  let tag ← match textField document "format" with
    | .ok value => pure value
    | .error _ => throwError "kernel recheck: missing serialization profile"
  unless tag == "in-formation.lean-expr-structural/0.1" do
    throwError "kernel recheck: unsupported serialization profile"
  let theorem ← match textField document "theorem" with
    | .ok value => pure value
    | .error _ => throwError "kernel recheck: missing theorem label"
  unless theorem == "KernelTrial.identity" do
    throwError "kernel recheck: unexpected theorem"
  let claimedType ← match field document "type" >>= decodeExpr with
    | .ok value => pure value
    | .error _ => throwError "kernel recheck: theorem type could not be reconstructed"
  let proof ← match field document "proof" >>= decodeExpr with
    | .ok value => pure value
    | .error _ => throwError "kernel recheck: proof term could not be reconstructed"
  -- Importantly, no KernelTrial module is imported here. We check the exact
  -- decoded term against the environment supplied by the standard Lean import.
  let env ← getEnv
  let inferred ← match Kernel.check env {} proof with
    | .ok ty => pure ty
    | .error _ => throwError "kernel recheck: reconstructed term rejected by Lean kernel"
  let equal ← match Kernel.isDefEq env {} inferred claimedType with
    | .ok same => pure same
    | .error _ => throwError "kernel recheck: theorem type comparison failed"
  unless equal do
    throwError "kernel recheck: reconstructed proof has a different theorem type"
  liftIO <| IO.println "SERIALIZED_TERM_KERNEL_ACCEPTED:KernelTrial.identity"
