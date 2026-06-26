package main

import "testing"

func TestClassifyFileSupported(t *testing.T) {
	supported := []string{
		"doc.txt", "sheet.xlsx", "legacy.xls", "data.csv", "report.pdf",
		"bundle.zip", "archive.7z", "blob.dat", "log.gz",
	}
	for _, name := range supported {
		if got := classifyFile(name); got != ClassSupported {
			t.Errorf("classifyFile(%q) = %v, want ClassSupported", name, got)
		}
	}
}

func TestClassifyFileCaseInsensitive(t *testing.T) {
	cases := map[string]Classification{
		"REPORT.PDF":   ClassSupported,
		"Data.CSV":     ClassSupported,
		"ARCHIVE.7Z":   ClassSupported,
		"control.CTRL": ClassSkip,
		"control.Ctl":  ClassSkip,
	}
	for name, want := range cases {
		if got := classifyFile(name); got != want {
			t.Errorf("classifyFile(%q) = %v, want %v", name, got, want)
		}
	}
}

func TestClassifyFileSkip(t *testing.T) {
	for _, name := range []string{"a.ctrl", "b.ctl", "nested/dir/c.ctrl"} {
		if got := classifyFile(name); got != ClassSkip {
			t.Errorf("classifyFile(%q) = %v, want ClassSkip", name, got)
		}
		if !isControlFile(name) {
			t.Errorf("isControlFile(%q) = false, want true", name)
		}
		if r := skipReasonFor(classifyFile(name)); r != skipReasonControlFile {
			t.Errorf("skipReasonFor(skip) = %q, want %q", r, skipReasonControlFile)
		}
	}
}

func TestClassifyFileUnsupported(t *testing.T) {
	for _, name := range []string{"image.png", "video.mp4", "noext", "script.sh", "a.docx"} {
		if got := classifyFile(name); got != ClassUnsupported {
			t.Errorf("classifyFile(%q) = %v, want ClassUnsupported", name, got)
		}
		if r := skipReasonFor(classifyFile(name)); r != skipReasonUnsupported {
			t.Errorf("skipReasonFor(unsupported) = %q, want %q", r, skipReasonUnsupported)
		}
	}
}

func TestOutputNameSupported(t *testing.T) {
	cases := map[string]string{
		"report.pdf":          "report.pdf.pgp",
		"doc.txt":             "doc.txt.pgp",
		"bundle.zip":          "bundle.zip.pgp",
		"nested/dir/data.csv": "nested/dir/data.csv.pgp",
	}
	for name, want := range cases {
		got, ok := outputName(name)
		if !ok {
			t.Errorf("outputName(%q) ok = false, want true", name)
			continue
		}
		if got != want {
			t.Errorf("outputName(%q) = %q, want %q", name, got, want)
		}
	}
}

func TestOutputNameNonSupported(t *testing.T) {
	for _, name := range []string{"control.ctrl", "control.ctl", "image.png", "noext"} {
		if got, ok := outputName(name); ok {
			t.Errorf("outputName(%q) = (%q, true), want ok=false", name, got)
		}
	}
}
