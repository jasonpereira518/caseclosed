"""Cycle 6: LLM intent classification with regex fallback, no-op
acknowledgments, conversation history in grounded answers."""
import unittest
from unittest.mock import MagicMock, patch


class ResolveIntentTests(unittest.TestCase):
    def test_llm_label_wins_over_the_regex(self):
        from services import chat_orchestrator as chat

        # The regex would call this a matter_update (no "?", no question word).
        with patch.object(chat, "classify_chat_intent", return_value="grounded_question"):
            self.assertEqual(chat.resolve_intent("Tell me about the weaknesses in our case"),
                             "grounded_question")

    def test_classifier_failure_falls_back_to_the_heuristic(self):
        from services import chat_orchestrator as chat

        with patch.object(chat, "classify_chat_intent", side_effect=RuntimeError("model down")):
            self.assertEqual(chat.resolve_intent("Find precedent for this claim"),
                             "legal_research")
            self.assertEqual(chat.resolve_intent("What does the contract say?"),
                             "grounded_question")

    def test_invalid_label_falls_back_to_the_heuristic(self):
        from services import chat_orchestrator as chat

        with patch.object(chat, "classify_chat_intent", return_value="write_a_poem"):
            self.assertEqual(chat.resolve_intent("I received the notice on March 4"),
                             "matter_update")


class ClassifyChatIntentUnitTests(unittest.TestCase):
    def _classify(self, model_text):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text=model_text)
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            return llm.classify_chat_intent("Some message"), chat

    def test_returns_the_model_label(self):
        label, _ = self._classify('{"intent": "acknowledgment"}')
        self.assertEqual(label, "acknowledgment")

    def test_raises_on_garbage_so_the_caller_falls_back(self):
        from services import llm

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text="not json at all")
        with patch.object(llm, "client") as client:
            client.chats.create.return_value = chat
            with self.assertRaises(ValueError):
                llm.classify_chat_intent("Some message")


class AcknowledgmentTests(unittest.TestCase):
    def test_acknowledgment_writes_nothing_and_is_ungrounded(self):
        from services import chat_orchestrator as chat

        matter = {"title": "Rivera", "messages": [], "description": "facts"}
        with patch.object(chat, "load_matter", return_value=matter), \
                patch.object(chat, "classify_chat_intent", return_value="acknowledgment"), \
                patch.object(chat, "update_job"), \
                patch.object(chat, "append_message"), \
                patch.object(chat, "patch_matter") as patch_matter, \
                patch.object(chat, "replace_matter_records") as replace_records:
            result = chat.process_chat_job("m1", "j1", {
                "requested_by": "u1", "payload": {"message": "thanks, got it"},
            })

        patch_matter.assert_not_called()
        replace_records.assert_not_called()
        self.assertEqual(result["intent"], "acknowledgment")
        self.assertFalse(result["grounded"])
        self.assertEqual(result["citations"], [])
        self.assertTrue(result["message"])


class HistoryInAnswersTests(unittest.TestCase):
    @patch("services.chat_orchestrator.answer_from_sources")
    @patch("services.chat_orchestrator.cancellation_requested", return_value=False)
    @patch("services.chat_orchestrator.update_job")
    @patch("services.chat_orchestrator.retrieve", return_value=[])
    def test_recent_turns_reach_the_grounder(self, retrieve, update, cancelled, answer):
        from services.chat_orchestrator import _answer

        answer.return_value = {"answer": "x", "citations": [], "grounded": True}
        matter = {
            "description": "facts",
            "analysis": {},
            "messages": [{"role": "user", "content": f"turn {i}"} for i in range(10)],
        }

        _answer("m1", "j1", "u1", "Explain that more simply", matter, "grounded_question")

        history = answer.call_args.kwargs.get("history")
        self.assertIsInstance(history, list)
        self.assertEqual(len(history), 6)  # capped at the most recent six turns
        self.assertEqual(history[-1]["content"], "turn 9")

    def test_grounding_prompt_marks_history_as_uncitable(self):
        from services import grounding

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text='{"answer": "ok", "citations": []}')
        with patch.object(grounding, "client") as client:
            client.chats.create.return_value = chat
            grounding.answer_from_sources(
                "Q?", [{"source_id": "s1", "title": "T", "locator": "L", "text": "body"}],
                history=[{"role": "user", "content": "earlier question"}],
            )
        prompt = chat.send_message.call_args[0][0]
        self.assertIn("RECENT CONVERSATION", prompt)
        self.assertIn("never cite", prompt.lower())
        self.assertIn("earlier question", prompt)

    def test_no_history_keeps_the_prompt_clean(self):
        from services import grounding

        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text='{"answer": "ok", "citations": []}')
        with patch.object(grounding, "client") as client:
            client.chats.create.return_value = chat
            grounding.answer_from_sources(
                "Q?", [{"source_id": "s1", "title": "T", "locator": "L", "text": "body"}])
        self.assertNotIn("RECENT CONVERSATION", chat.send_message.call_args[0][0])


class MatterUpdateHonestyTests(unittest.TestCase):
    @patch("services.chat_orchestrator.extract_structured_analysis", return_value={})
    @patch("services.chat_orchestrator.patch_matter")
    @patch("services.chat_orchestrator.update_job")
    def test_the_canned_confirmation_is_not_grounded(self, update, patch_m, extract):
        from services.chat_orchestrator import _update_matter

        result = _update_matter("m1", "j1", "u1", "I received the notice on March 4",
                                {"description": ""})

        self.assertFalse(result["grounded"])
        self.assertEqual(result["citations"], [])


if __name__ == "__main__":
    unittest.main()
