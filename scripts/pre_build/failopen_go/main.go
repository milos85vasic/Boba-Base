// failopengo — syntax-tree (go/ast) detector for two Go fail-open idioms, used
// by scripts/pre_build/check_fail_open_unanalysed_langs.sh (BOB-191).
//
// Why an AST and not a regex: a regex arm for Go immediately manufactures
// false positives — `if err != nil { return false }` in a validator is
// fail-CLOSED. Only shapes that are fail-open by construction are reported:
//
//	GO-EMPTY-ERR-BRANCH   an if-statement whose condition compares an error
//	                      identifier (err, or a name ending in Err/err) with
//	                      nil using != and whose body has NO statements —
//	                      the error is observed and then dropped.
//	GO-SWALLOWED-PANIC    a deferred function literal whose only statement is
//	                      a bare recover() call — every panic is swallowed.
//
// Honest boundary: an error discarded through the blank identifier
// (`x, _ := f()`) needs type information to separate errors from other values
// and is NOT detected here; that belongs to a type-aware tool (errcheck).
//
// Usage:  go run . <file.go>...
// Output: <path>:<line>: <RULE> <detail>   one line per hit
// Exit:   0 no hits, 1 hits, 2 a file could not be parsed
package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strings"
)

func isErrIdent(e ast.Expr) bool {
	id, ok := e.(*ast.Ident)
	if !ok {
		return false
	}
	n := id.Name
	return n == "err" || strings.HasSuffix(n, "Err") || strings.HasSuffix(n, "err")
}

func isNil(e ast.Expr) bool {
	id, ok := e.(*ast.Ident)
	return ok && id.Name == "nil"
}

func errNotNil(cond ast.Expr) bool {
	be, ok := cond.(*ast.BinaryExpr)
	if !ok || be.Op != token.NEQ {
		return false
	}
	return (isErrIdent(be.X) && isNil(be.Y)) || (isErrIdent(be.Y) && isNil(be.X))
}

func isBareRecover(s ast.Stmt) bool {
	es, ok := s.(*ast.ExprStmt)
	if !ok {
		return false
	}
	ce, ok := es.X.(*ast.CallExpr)
	if !ok {
		return false
	}
	id, ok := ce.Fun.(*ast.Ident)
	return ok && id.Name == "recover" && len(ce.Args) == 0
}

func main() {
	fset := token.NewFileSet()
	hits, bad := 0, 0
	for _, path := range os.Args[1:] {
		f, err := parser.ParseFile(fset, path, nil, 0)
		if err != nil {
			fmt.Fprintf(os.Stderr, "PARSE-ERROR %s: %v\n", path, err)
			bad++
			continue
		}
		ast.Inspect(f, func(n ast.Node) bool {
			switch x := n.(type) {
			case *ast.IfStmt:
				if errNotNil(x.Cond) && len(x.Body.List) == 0 {
					fmt.Printf("%s:%d: GO-EMPTY-ERR-BRANCH error checked then dropped (empty if body)\n",
						path, fset.Position(x.Pos()).Line)
					hits++
				}
			case *ast.DeferStmt:
				if fl, ok := x.Call.Fun.(*ast.FuncLit); ok && len(fl.Body.List) == 1 && isBareRecover(fl.Body.List[0]) {
					fmt.Printf("%s:%d: GO-SWALLOWED-PANIC deferred bare recover() discards every panic\n",
						path, fset.Position(x.Pos()).Line)
					hits++
				}
			}
			return true
		})
	}
	if bad > 0 {
		os.Exit(2)
	}
	if hits > 0 {
		os.Exit(1)
	}
}
