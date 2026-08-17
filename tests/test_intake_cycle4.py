"""Cycle 4: editable intake (prefill + marker replace), authoritative intake
jurisdiction, and the party-role wired end-to-end."""
import unittest
from unittest.mock import MagicMock, patch

from app import app
from models.user import User


def _sign_in(client):
    with client.session_transaction() as session:
        session["_user_id"] = "test-user"
        session["_fresh"] = True


def _user():
    return User(id="test-user", email="l@example.com", name="Jordan", profile_pic=None)


def _submit(client, ctx, payload=None):
    body = {
        "context_id": "matter-1",
        "case_title": "Smith v. Jones",
        "legal_category": "Contract",
        "jurisdiction": "Ohio",
        "user_role": "Plaintiff",
        "description": "Breach of contract.",
    }
    body.update(payload or {})
    with patch("routes.intake.get_or_create_context", return_value=ctx), \
            patch("routes.intake.create_job",
                  return_value=({"job_id": "j1", "status": "queued"}, True)), \
            patch("routes.intake.enqueue_job"):
        return client.post("/intake", json=body)


class IntakeReplaceTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    @patch("models.user.load_user")
    def test_first_submission_appends_a_marked_block(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "Client narrative.", "messages": []}

        response = _submit(self.client, ctx)

        self.assertEqual(response.status_code, 202)
        self.assertIn("===== CASE INTAKE =====", ctx["description"])
        self.assertIn("===== END CASE INTAKE =====", ctx["description"])
        self.assertTrue(ctx["description"].startswith("Client narrative."))

    @patch("models.user.load_user")
    def test_resubmission_replaces_the_marked_block(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "Client narrative.", "messages": []}

        _submit(self.client, ctx, {"legal_category": "Contract"})
        _submit(self.client, ctx, {"legal_category": "Employment"})

        self.assertEqual(ctx["description"].count("===== CASE INTAKE ====="), 1)
        self.assertIn("Employment", ctx["description"])
        self.assertNotIn("Category: Contract", ctx["description"])
        self.assertTrue(ctx["description"].startswith("Client narrative."))

    @patch("models.user.load_user")
    def test_title_follows_intake_until_manually_renamed(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "", "messages": []}

        _submit(self.client, ctx, {"case_title": "Smith v. Jones"})
        self.assertEqual(ctx["title"], "Smith v. Jones")

        # Still tracking the intake title: a corrected intake retitles the matter.
        _submit(self.client, ctx, {"case_title": "Smith v. Jones Logistics"})
        self.assertEqual(ctx["title"], "Smith v. Jones Logistics")

        # A manual rename wins forever after.
        ctx["title"] = "My renamed matter"
        _submit(self.client, ctx, {"case_title": "Third title"})
        self.assertEqual(ctx["title"], "My renamed matter")

    @patch("models.user.load_user")
    def test_role_is_persisted_lowercase(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "", "messages": []}

        _submit(self.client, ctx, {"user_role": "Plaintiff"})

        self.assertEqual(ctx["role"], "plaintiff")

    @patch("models.user.load_user")
    def test_update_is_labelled_in_the_chat_log(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)
        ctx = {"title": "New Session", "description": "", "messages": []}

        _submit(self.client, ctx)
        self.assertIn("CASE INTAKE", ctx["messages"][0]["content"])
        self.assertNotIn("UPDATED", ctx["messages"][0]["content"])

        _submit(self.client, ctx)
        self.assertIn("CASE INTAKE (UPDATED)", ctx["messages"][1]["content"])


class MatterRoleEndpointTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_unauthenticated_gets_401_json(self):
        response = self.client.post("/matter/role", json={"context_id": "m1", "role": "plaintiff"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "unauthorized"})

    @patch("routes.context.patch_matter")
    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_valid_role_is_patched_into_state(self, load_user, belongs, patch_fn):
        load_user.return_value = _user()
        _sign_in(self.client)
        belongs.return_value = True

        response = self.client.post("/matter/role",
                                    json={"context_id": "m1", "role": "Third Party"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], "third party")
        patch_fn.assert_called_once_with("m1", "test-user", state={"role": "third party"})

    @patch("models.user.load_user")
    def test_unknown_role_is_rejected(self, load_user):
        load_user.return_value = _user()
        _sign_in(self.client)

        response = self.client.post("/matter/role",
                                    json={"context_id": "m1", "role": "prosecutor"})

        self.assertEqual(response.status_code, 400)

    @patch("routes.context.context_belongs_to_user")
    @patch("models.user.load_user")
    def test_inaccessible_matter_is_404(self, load_user, belongs):
        load_user.return_value = _user()
        _sign_in(self.client)
        belongs.return_value = False

        response = self.client.post("/matter/role",
                                    json={"context_id": "m1", "role": "plaintiff"})

        self.assertEqual(response.status_code, 404)


class JurisdictionPreferenceTests(unittest.TestCase):
    def test_intake_jurisdiction_wins(self):
        from services.chat_orchestrator import _jurisdiction

        self.assertEqual(
            _jurisdiction({"jurisdiction": "California"}, {"jurisdiction": "Ohio"}),
            "Ohio",
        )

    def test_extraction_is_the_fallback(self):
        from services.chat_orchestrator import _jurisdiction

        self.assertEqual(_jurisdiction({"jurisdiction": "California"}, {}), "California")
        self.assertEqual(_jurisdiction({"jurisdictions": ["Texas", "Federal"]}, None), "Texas")
        self.assertIsNone(_jurisdiction({}, None))

    @patch("services.chat_orchestrator.answer_from_sources")
    @patch("services.chat_orchestrator.cancellation_requested", return_value=False)
    @patch("services.chat_orchestrator.update_job")
    @patch("services.chat_orchestrator.retrieve", return_value=[])
    def test_grounded_answers_use_intake_jurisdiction_and_role(
        self, retrieve, update_job, cancelled, answer
    ):
        from services.chat_orchestrator import _answer

        answer.return_value = {"answer": "x", "citations": [], "grounded": True}
        matter = {
            "description": "facts",
            "analysis": {"jurisdiction": "California"},
            "intake": {"jurisdiction": "Ohio"},
            "role": "plaintiff",
        }

        _answer("m1", "j1", "u1", "What is our exposure?", matter, "grounded_question")

        self.assertEqual(retrieve.call_args.kwargs.get("jurisdiction"), "Ohio")
        self.assertEqual(answer.call_args.kwargs.get("client_role"), "plaintiff")


class RolePromptTests(unittest.TestCase):
    def _grounding_prompt(self, **kwargs):
        from services import grounding

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text='{"answer": "ok", "citations": []}')
        with patch.object(grounding, "client") as client:
            client.chats.create.return_value = chat
            grounding.answer_from_sources(
                "Q?", [{"source_id": "s1", "title": "T", "locator": "L", "text": "body"}],
                **kwargs,
            )
        return chat.send_message.call_args[0][0]

    def test_answer_prompt_carries_the_client_role(self):
        prompt = self._grounding_prompt(client_role="plaintiff")
        self.assertIn("represents the plaintiff", prompt)

    def test_answer_prompt_is_unchanged_without_a_role(self):
        prompt = self._grounding_prompt()
        self.assertNotIn("represents the", prompt)

    def test_draft_prompt_carries_the_client_role(self):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text="MEMORANDUM")
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            llm.draft_legal_document(
                {"analysis": {}, "summary": "s", "cases": [], "role": "defendant"}, "memo"
            )
        prompt = chat.send_message.call_args[0][0]
        self.assertIn("represents the defendant", prompt)


if __name__ == "__main__":
    unittest.main()
