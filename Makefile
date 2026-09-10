PREFIX  ?= /usr/local
DESTDIR ?=
BINDIR   = $(DESTDIR)$(PREFIX)/bin
MANDIR   = $(DESTDIR)$(PREFIX)/share/man/man1
APPSDIR  = $(DESTDIR)$(PREFIX)/share/applications
SHAREDIR = $(DESTDIR)$(PREFIX)/share/gtasks-panel
VERSION := $(shell dpkg-parsechangelog -S Version 2>/dev/null || echo 0.0.0)

.PHONY: check install uninstall deb clean

check:
	python3 -c "import ast; ast.parse(open('bin/gtasks-panel').read(), 'bin/gtasks-panel')"
	python3 -c "import ast; ast.parse(open('bin/gtasks-window').read(), 'bin/gtasks-window')"
	python3 -m compileall -q -f gtasks_panel
	@if command -v desktop-file-validate >/dev/null 2>&1; then \
	    desktop-file-validate data/*.desktop; fi
	@# man exits 0 on warnings, so the check fails on any warning output.
	@if command -v man >/dev/null 2>&1; then \
	    out=$$(man --warnings -l man/gtasks-panel.1 man/gtasks-window.1 2>&1 >/dev/null); \
	    if [ -n "$$out" ]; then echo "$$out"; exit 1; fi; \
	fi
	@if python3 -c "import pytest" 2>/dev/null; then python3 -m pytest -q -p no:cacheprovider tests; \
	else echo "pytest not installed, tests skipped"; fi
	@# compileall and pytest leave byte code behind. The package ships none.
	@find gtasks_panel -name __pycache__ -type d -exec rm -rf {} +

install:
	install -Dm755 bin/gtasks-panel  $(BINDIR)/gtasks-panel
	install -Dm755 bin/gtasks-window $(BINDIR)/gtasks-window
	@# The private package. Only .py files, no byte code (lintian flags it).
	@for f in $$(find gtasks_panel -name '*.py' -not -path '*/__pycache__/*' | sort); do \
	    install -Dm644 "$$f" "$(SHAREDIR)/$$f" || exit 1; \
	done
	install -Dm644 man/gtasks-panel.1  $(MANDIR)/gtasks-panel.1
	install -Dm644 man/gtasks-window.1 $(MANDIR)/gtasks-window.1
	install -Dm644 data/com.belneiski.gtasks.desktop $(APPSDIR)/com.belneiski.gtasks.desktop
	@# Optional: ship your own OAuth client so installs only need --auth.
	@if [ -f share/client_secret.json ]; then \
	    install -Dm644 share/client_secret.json $(SHAREDIR)/client_secret.json; \
	    echo "Packaged share/client_secret.json as $(SHAREDIR)/client_secret.json"; \
	fi

uninstall:
	rm -f $(BINDIR)/gtasks-panel $(BINDIR)/gtasks-window
	rm -f $(MANDIR)/gtasks-panel.1 $(MANDIR)/gtasks-window.1
	rm -f $(APPSDIR)/com.belneiski.gtasks.desktop
	rm -rf $(SHAREDIR)

deb: check
	dpkg-buildpackage -us -uc -b
	mkdir -p dist
	mv ../gtasks-panel_$(VERSION)_all.deb ../gtasks-panel_$(VERSION)_*.buildinfo ../gtasks-panel_$(VERSION)_*.changes dist/
	@echo "Built dist/gtasks-panel_$(VERSION)_all.deb"

clean:
	rm -rf dist debian/gtasks-panel debian/.debhelper debian/files debian/*.substvars debian/debhelper-build-stamp \
	    debian/*.debhelper.log bin/__pycache__ tests/__pycache__ .pytest_cache
	@find gtasks_panel -name __pycache__ -type d -exec rm -rf {} +
