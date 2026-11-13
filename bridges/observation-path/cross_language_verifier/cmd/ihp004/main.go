package main

import (
	"flag"
	"fmt"
	"os"

	verifier "github.com/kier73/in-formation-space/bridges/observation-path/cross_language_verifier"
)

func main() {
	if len(os.Args) < 2 || os.Args[1] != "verify" {
		fmt.Fprintln(os.Stderr, "usage: ihp004 verify --source host-a.json --receiver host-b.json --report report.json --predicate predicate.json [--python-report diverse-report.json]")
		os.Exit(2)
	}
	fs := flag.NewFlagSet("verify", flag.ExitOnError)
	sourcePath := fs.String("source", "", "source-host record JSON")
	receiverPath := fs.String("receiver", "", "receiver-host record JSON")
	reportPath := fs.String("report", "", "output report JSON")
	predicatePath := fs.String("predicate", "", "output attestation predicate JSON")
	pythonReportPath := fs.String("python-report", "", "optional Python diverse report to compare")
	_ = fs.Parse(os.Args[2:])
	if *sourcePath == "" || *receiverPath == "" || *reportPath == "" || *predicatePath == "" {
		fmt.Fprintln(os.Stderr, "source, receiver, report, and predicate paths are required")
		os.Exit(2)
	}
	identity, err := verifier.IdentityFromEnv()
	fatalIf(err)
	source, sourceBytes, err := verifier.ReadCanonicalFile(*sourcePath)
	fatalIf(err)
	receiver, receiverBytes, err := verifier.ReadCanonicalFile(*receiverPath)
	fatalIf(err)
	report, err := verifier.Reconstruct(source, sourceBytes, receiver, receiverBytes, identity)
	fatalIf(err)
	fatalIf(verifier.WriteJSON(*reportPath, report))
	reportBytes, err := os.ReadFile(*reportPath)
	fatalIf(err)
	predicate, err := verifier.BuildPredicate(report, reportBytes, identity)
	fatalIf(err)
	fatalIf(verifier.WriteJSON(*predicatePath, predicate))
	if *pythonReportPath != "" {
		pythonReport, _, err := verifier.ReadCanonicalFile(*pythonReportPath)
		fatalIf(err)
		fatalIf(verifier.ValidateReportParity(report, pythonReport))
	}
	fmt.Printf("Go cross-language reconstruction succeeded: %s -> %s\n", report["causal_reconstruction"].(map[string]any)["predecessor_span_digest"], report["causal_reconstruction"].(map[string]any)["successor_span_digest"])
}

func fatalIf(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "ihp004-go:", err)
		os.Exit(1)
	}
}
