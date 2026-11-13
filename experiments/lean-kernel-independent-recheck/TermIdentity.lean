import Lean
import KernelTrial

open Lean Elab Command

/-!
Versioned, fail-closed structural serialization of a *closed* Lean 4.15 Expr.
Binder names are intentionally omitted (de Bruijn indices retain scope).
Metadata, free variables, and metavariables are rejected rather than
silently creating misleading fingerprints.
-/

private def obj (kind : String) (fields : List (String × Json) := []) : Json :=
  Json.mkObj (("kind", toJson kind) :: fields)

private partial def encodeName : Name → Json
  | .anonymous => obj "anonymous"
  | .str prefix value => obj "str" [("prefix", encodeName prefix), ("value", toJson value)]
  | .num prefix value => obj "num" [("prefix", encodeName prefix), ("value", toJson value)]

private partial def encodeLevel : Level → Except String Json
  | .zero => pure (obj "zero")
  | .succ u => do
      let value ← encodeLevel u
      pure (obj "succ" [("of", value)])
  | .max a b => do
      let left ← encodeLevel a
      let right ← encodeLevel b
      pure (obj "max" [("left", left), ("right", right)])
  | .imax a b => do
      let left ← encodeLevel a
      let right ← encodeLevel b
      pure (obj "imax" [("left", left), ("right", right)])
  | .param name => pure (obj "param" [("name", encodeName name)])
  | .mvar _ => .error "unresolved universe metavariable"

private def encodeBinderInfo : BinderInfo → String
  | .default => "default"
  | .implicit => "implicit"
  | .strictImplicit => "strictImplicit"
  | .instImplicit => "instImplicit"

private partial def encodeExpr : Expr → Except String Json
  | .bvar idx => pure (obj "bvar" [("index", toJson idx)])
  | .fvar _ => .error "free variable in stored declaration"
  | .mvar _ => .error "unresolved expression metavariable"
  | .sort level => do
      let value ← encodeLevel level
      pure (obj "sort" [("level", value)])
  | .const name levels => do
      let values ← levels.mapM encodeLevel
      pure (obj "const" [("name", encodeName name), ("levels", toJson values)])
  | .app f a => do
      let funExpr ← encodeExpr f
      let argExpr ← encodeExpr a
      pure (obj "app" [("fn", funExpr), ("arg", argExpr)])
  | .lam _ type body info => do
      let domain ← encodeExpr type
      let result ← encodeExpr body
      pure (obj "lam" [("domain", domain), ("body", result),
                        ("binderInfo", toJson (encodeBinderInfo info))])
  | .forallE _ type body info => do
      let domain ← encodeExpr type
      let result ← encodeExpr body
      pure (obj "forallE" [("domain", domain), ("body", result),
                            ("binderInfo", toJson (encodeBinderInfo info))])
  | .letE _ type value body nondep => do
      let domain ← encodeExpr type
      let definition ← encodeExpr value
      let result ← encodeExpr body
      pure (obj "letE" [("type", domain), ("value", definition),
                         ("body", result), ("nondep", toJson nondep)])
  | .lit (.natVal n) => pure (obj "natVal" [("value", toJson n)])
  | .lit (.strVal s) => pure (obj "strVal" [("value", toJson s)])
  | .mdata _ _ => .error "metadata expression: serialization deliberately unsupported"
  | .proj typeName idx structure => do
      let value ← encodeExpr structure
      pure (obj "proj" [("typeName", encodeName typeName),
                        ("index", toJson idx), ("structure", value)])

run_cmd do
  let env ← getEnv
  let some declaration := env.find? `KernelTrial.identity
    | throwError "KernelTrial.identity is not present in the elaborated environment"
  let some proof := declaration.value?
    | throwError "KernelTrial.identity has no elaborated proof value"
  let statement ← match encodeExpr declaration.type with
    | .ok value => pure value
    | .error reason => throwError "theorem-type encoding failed: {reason}"
  let term ← match encodeExpr proof with
    | .ok value => pure value
    | .error reason => throwError "proof-term encoding failed: {reason}"
  let output := Json.mkObj [
    ("format", toJson ("in-formation.lean-expr-structural/0.1" : String)),
    ("theorem", toJson ("KernelTrial.identity" : String)),
    ("type", statement),
    ("proof", term)]
  liftIO <| IO.FS.writeFile "term-identity.json" output.compress
