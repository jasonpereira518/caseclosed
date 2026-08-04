(function () {
    "use strict";

    const header = document.querySelector("[data-header]");
    const navToggle = document.querySelector("[data-nav-toggle]");
    const navLinks = document.querySelector("[data-nav-links]");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function updateHeader() {
        if (header) header.classList.toggle("scrolled", window.scrollY > 12);
    }

    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });

    function closeNavigation() {
        if (!navToggle || !navLinks) return;
        navToggle.setAttribute("aria-expanded", "false");
        navLinks.classList.remove("open");
        document.body.classList.remove("nav-open");
    }

    if (navToggle && navLinks) {
        navToggle.addEventListener("click", function () {
            const shouldOpen = navToggle.getAttribute("aria-expanded") !== "true";
            navToggle.setAttribute("aria-expanded", String(shouldOpen));
            navLinks.classList.toggle("open", shouldOpen);
            document.body.classList.toggle("nav-open", shouldOpen);
        });

        navLinks.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", closeNavigation);
        });

        window.addEventListener("resize", function () {
            if (window.innerWidth > 820) closeNavigation();
        });
    }

    const workspaceDemo = document.querySelector("[data-workspace-demo]");
    const heroTabs = Array.from(document.querySelectorAll("[data-hero-tab]"));
    const heroPanels = Array.from(document.querySelectorAll("[data-hero-panel]"));

    if (workspaceDemo && !reduceMotion && "IntersectionObserver" in window) {
        workspaceDemo.classList.add("demo-motion-ready");
    }

    function selectHeroPanel(panelName) {
        heroTabs.forEach(function (tab) {
            const isActive = tab.dataset.heroTab === panelName;
            tab.classList.toggle("active", isActive);
            tab.setAttribute("aria-selected", String(isActive));
            tab.setAttribute("tabindex", isActive ? "0" : "-1");
        });

        heroPanels.forEach(function (panel) {
            const isActive = panel.dataset.heroPanel === panelName;
            panel.classList.toggle("active", isActive);
            panel.setAttribute("aria-hidden", String(!isActive));
        });

    }

    heroTabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            selectHeroPanel(tab.dataset.heroTab);
        });
    });

    const revealItems = document.querySelectorAll(".reveal");
    const fragmentedDemo = document.querySelector(".fragmented-demo");
    const workflowSteps = document.querySelector(".workflow-steps");

    if (reduceMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach(function (item) {
            item.classList.add("is-visible");
        });
        if (fragmentedDemo) fragmentedDemo.classList.add("in-view");
        if (workflowSteps) workflowSteps.classList.add("in-view");
        if (workspaceDemo) workspaceDemo.classList.add("demo-running");
    } else {
        const revealObserver = new IntersectionObserver(function (entries, observer) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: "0px 0px -45px" });

        revealItems.forEach(function (item) {
            revealObserver.observe(item);
        });

        if (fragmentedDemo) {
            const fragmentObserver = new IntersectionObserver(function (entries, observer) {
                if (!entries[0].isIntersecting) return;
                fragmentedDemo.classList.add("in-view");
                observer.unobserve(fragmentedDemo);
            }, { threshold: 0.3 });
            fragmentObserver.observe(fragmentedDemo);
        }

        if (workflowSteps) {
            const workflowObserver = new IntersectionObserver(function (entries, observer) {
                if (!entries[0].isIntersecting) return;
                workflowSteps.classList.add("in-view");
                observer.unobserve(workflowSteps);
            }, { threshold: 0.35 });
            workflowObserver.observe(workflowSteps);
        }

        if (workspaceDemo) {
            const workspaceObserver = new IntersectionObserver(function (entries, observer) {
                if (!entries[0].isIntersecting) return;
                workspaceDemo.classList.add("demo-running");
                observer.unobserve(workspaceDemo);
            }, { threshold: 0.22 });
            workspaceObserver.observe(workspaceDemo);
        }
    }

    const featureButtons = Array.from(document.querySelectorAll("[data-feature]"));
    const featureLayout = document.querySelector(".feature-layout");
    const featureSection = document.querySelector(".product-section");
    const featureList = document.querySelector(".feature-list");
    const previewState = document.querySelector("[data-preview-state]");
    const previewCanvas = document.querySelector("[data-preview-canvas]");
    const previewEyebrow = document.querySelector("[data-preview-eyebrow]");
    const previewTitle = document.querySelector("[data-preview-title]");
    const previewRecords = document.querySelector("[data-preview-records]");
    let featureTimer = null;
    let featureIndex = 0;
    let userSelectedFeature = false;

    const featureContent = {
        record: {
            status: "Record organized",
            eyebrow: "MATTER RECORD",
            title: "Four documents, one working record",
            className: "",
            rows: [
                ["PDF", "Complaint.pdf", "42 pages · Analyzed", "✓"],
                ["PDF", "Incident report.pdf", "8 pages · Analyzed", "✓"],
                ["DOC", "Witness statement.docx", "6 pages · Analyzed", "✓"],
                ["TXT", "Client notes.txt", "Updated today", "✓"]
            ]
        },
        timeline: {
            status: "14 events connected",
            eyebrow: "CHRONOLOGY",
            title: "The facts, arranged in time",
            className: "timeline-state",
            rows: [
                ["MAR 03", "Safety concern raised", "Client email to supervisor", ""],
                ["MAR 18", "Written complaint submitted", "Regional management notified", ""],
                ["MAR 24", "Performance warning issued", "First warning in personnel file", ""],
                ["APR 05", "Employment terminated", "18 days after complaint", ""]
            ]
        },
        issues: {
            status: "4 issues identified",
            eyebrow: "STRUCTURED ANALYSIS",
            title: "Legal questions connected to the facts",
            className: "issue-state",
            rows: [
                ["01", "Protected activity", "Internal safety complaint", "Open"],
                ["02", "Employer notice", "Written escalation received", "Review"],
                ["03", "Adverse action", "Termination and warning", "Clear"],
                ["04", "Causation", "Temporal proximity", "Open"]
            ]
        },
        authority: {
            status: "9 authorities ranked",
            eyebrow: "CASE RESEARCH",
            title: "Authority ranked by matter fit",
            className: "authority-state",
            rows: [
                ["92", "Kwan v. Andalex Group LLC", "2d Cir. · Temporal proximity", "View"],
                ["88", "Zann Kwan v. Andalex", "Retaliation framework", "View"],
                ["84", "Gorman-Bakos v. Cornell", "Causation analysis", "View"],
                ["79", "Summa v. Hofstra University", "Protected activity", "View"]
            ]
        },
        draft: {
            status: "Outline ready",
            eyebrow: "LEGAL MEMORANDUM",
            title: "A first draft grounded in this matter",
            className: "draft-state",
            rows: [
                ["", "Question Presented", "Whether Rivera can establish a prima facie retaliation claim based on the written safety complaint and termination eighteen days later.", ""],
                ["", "Short Answer", "The current record supports a plausible claim, subject to further review of the employer's stated reason and comparator evidence.", ""],
                ["", "Analysis", "The memorandum connects the protected activity, notice, adverse action, and causation authorities collected in this matter.", ""]
            ]
        }
    };

    function createPreviewRow(row, index) {
        const wrapper = document.createElement("div");
        wrapper.style.animationDelay = String(index * 55) + "ms";

        const badge = document.createElement("span");
        badge.textContent = row[0];
        const copy = document.createElement("p");
        const title = document.createElement("strong");
        title.textContent = row[1];
        const detail = document.createElement("small");
        detail.textContent = row[2];
        const action = document.createElement("b");
        action.textContent = row[3];

        copy.append(title, detail);
        wrapper.append(badge, copy, action);
        return wrapper;
    }

    function selectFeature(featureName, fromUser) {
        const content = featureContent[featureName];
        if (!content || !previewRecords) return;

        featureButtons.forEach(function (button) {
            const isActive = button.dataset.feature === featureName;
            button.classList.toggle("active", isActive);
            button.setAttribute("aria-selected", String(isActive));
            if (isActive) {
                featureIndex = featureButtons.indexOf(button);
                if (!fromUser && featureList && window.innerWidth <= 600) {
                    featureList.scrollTo({
                        left: Math.max(0, button.offsetLeft - 24),
                        behavior: reduceMotion ? "auto" : "smooth"
                    });
                }
            }
        });

        if (previewState) previewState.textContent = content.status;
        if (previewEyebrow) previewEyebrow.textContent = content.eyebrow;
        if (previewTitle) previewTitle.textContent = content.title;
        if (previewCanvas) previewCanvas.dataset.state = featureName;

        previewRecords.className = "preview-records" + (content.className ? " " + content.className : "");
        previewRecords.replaceChildren();
        content.rows.forEach(function (row, index) {
            previewRecords.appendChild(createPreviewRow(row, index));
        });

        if (fromUser) {
            userSelectedFeature = true;
            stopFeatureDemo();
        }
    }

    featureButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            selectFeature(button.dataset.feature, true);
        });
    });

    function startFeatureDemo() {
        if (reduceMotion || userSelectedFeature || featureTimer || featureButtons.length < 2) return;
        if (featureLayout) featureLayout.classList.add("is-auto");
        featureTimer = window.setInterval(function () {
            if (document.hidden) return;
            featureIndex = (featureIndex + 1) % featureButtons.length;
            selectFeature(featureButtons[featureIndex].dataset.feature, false);
        }, 5600);
    }

    function stopFeatureDemo() {
        if (featureTimer) window.clearInterval(featureTimer);
        featureTimer = null;
        if (featureLayout) featureLayout.classList.remove("is-auto");
    }

    if (featureSection && featureButtons.length && !reduceMotion && "IntersectionObserver" in window) {
        const featureObserver = new IntersectionObserver(function (entries) {
            if (entries[0].isIntersecting) startFeatureDemo();
            else stopFeatureDemo();
        }, { threshold: 0.3 });
        featureObserver.observe(featureSection);
    }

    const outcomeRow = document.querySelector(".outcome-row");
    const outcomeNumbers = Array.from(document.querySelectorAll("[data-count]"));

    function animateOutcomeNumbers() {
        const duration = 780;
        const startedAt = performance.now();

        outcomeNumbers.forEach(function (number) {
            number.textContent = "0";
        });

        function draw(now) {
            const progress = Math.min(1, (now - startedAt) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            outcomeNumbers.forEach(function (number) {
                const target = Number(number.dataset.count);
                number.textContent = String(Math.round(target * eased));
            });
            if (progress < 1) window.requestAnimationFrame(draw);
        }

        window.requestAnimationFrame(draw);
    }

    if (outcomeRow && outcomeNumbers.length && !reduceMotion && "IntersectionObserver" in window) {
        const outcomeObserver = new IntersectionObserver(function (entries, observer) {
            if (!entries[0].isIntersecting) return;
            animateOutcomeNumbers();
            observer.unobserve(outcomeRow);
        }, { threshold: 0.45 });
        outcomeObserver.observe(outcomeRow);
    }

    const faqItems = document.querySelectorAll(".faq-list details");
    faqItems.forEach(function (item) {
        item.addEventListener("toggle", function () {
            if (!item.open) return;
            faqItems.forEach(function (otherItem) {
                if (otherItem !== item) otherItem.removeAttribute("open");
            });
        });
    });
})();
