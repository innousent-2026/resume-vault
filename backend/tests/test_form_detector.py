from form_detector import analyze_form, choose_option, classify_field, detect_ats, field_signature


def field(**kw):
    base = {"field_id": "f1", "selector": "#f1", "type": "text", "name": "", "id": "",
            "label": "", "placeholder": "", "autocomplete": "", "aria_label": ""}
    base.update(kw)
    return base


VALUES = {
    "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com",
    "phone": "555-123-4567", "linkedin": "https://linkedin.com/in/janedoe",
    "work_authorized": "Yes", "requires_sponsorship": "No", "eeo_gender": "Decline to self-identify",
}


def test_detect_ats_from_host():
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/123") == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/abc") == "lever"
    assert detect_ats("https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/x") == "workday"
    assert detect_ats("https://careers.acme.com/apply") == "unknown"


def test_autocomplete_beats_everything():
    result = classify_field(field(autocomplete="given-name", name="q7_input", label="Q7"))
    assert result["canonical"] == "first_name"
    assert result["confidence"] > 0.95


def test_label_matching_across_common_phrasings():
    cases = {
        "First Name *": "first_name",
        "Last name": "last_name",
        "Email Address": "email",
        "Mobile phone": "phone",
        "LinkedIn Profile": "linkedin",
        "Desired salary": "desired_salary",
        "Are you legally authorized to work in the United States?": "work_authorized",
        "Will you now or in the future require sponsorship?": "requires_sponsorship",
        "How did you hear about us?": "how_did_you_hear",
    }
    for label, expected in cases.items():
        assert classify_field(field(label=label))["canonical"] == expected, label


def test_sponsorship_rule_wins_over_work_authorization():
    label = "Will you now or in the future require visa sponsorship to work in the US?"
    assert classify_field(field(label=label))["canonical"] == "requires_sponsorship"


def test_signature_and_attestation_fields_are_never_filled():
    for label in ["Electronic Signature", "I certify the above is true", "Social Security Number",
                  "Date of Birth", "Password"]:
        result = classify_field(field(label=label))
        assert result["canonical"] is None, label


def test_eeo_fields_skipped_unless_opted_in():
    fields = [field(field_id="g", label="Gender", type="select",
                    options=[{"label": "Male", "value": "m"}, {"label": "Decline to self-identify", "value": "d"}])]
    off = analyze_form(fields, VALUES, url="https://boards.greenhouse.io/acme")
    assert off["plan"] == []
    assert "demographic" in off["skipped"][0]["skip_reason"]

    on = analyze_form(fields, VALUES, url="https://boards.greenhouse.io/acme", include_sensitive=True)
    assert on["plan"][0]["value"] == "d"


def test_file_inputs_are_left_to_the_user():
    result = analyze_form([field(field_id="r", type="file", label="Resume/CV")], VALUES)
    assert result["plan"] == []
    assert "manually" in result["skipped"][0]["skip_reason"]


def test_select_option_matching():
    options = [{"label": "Yes", "value": "1"}, {"label": "No", "value": "0"}]
    assert choose_option("Yes", options) == "1"
    assert choose_option("No", options) == "0"
    assert choose_option("Maybe", options) is None


def test_analyze_form_builds_plan_and_reports_no_submit():
    fields = [
        field(field_id="a", name="first_name", label="First Name"),
        field(field_id="b", name="last_name", label="Last Name"),
        field(field_id="c", name="email", label="Email"),
        field(field_id="d", name="mystery_q", label="Describe your favorite process"),
    ]
    result = analyze_form(fields, VALUES, url="https://boards.greenhouse.io/acme")
    assert result["ats"] == "greenhouse"
    assert {p["canonical"] for p in result["plan"]} == {"first_name", "last_name", "email"}
    assert result["high_confidence"] == 3
    assert len(result["skipped"]) == 1


def test_learned_mapping_overrides_rules():
    f = field(field_id="x", name="cand_q_00123", label="Q1")
    signature = field_signature(f)
    result = classify_field(f, learned={signature: "phone"})
    assert result["canonical"] == "phone"
    assert result["matched_on"] == "learned"


def test_signature_ignores_generated_numeric_suffixes():
    a = field(name="input_1234567", id="field_98765", label="Email")
    b = field(name="input_7654321", id="field_12345", label="Email")
    assert field_signature(a) == field_signature(b)
