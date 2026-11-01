"""Provider failures are simulated; no real keys, requests, or financial records."""
import unittest
from unittest.mock import MagicMock, patch
import test_environment
import llm_coach


class AIResilienceTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(llm_coach, MODEL_NAME='primary', FALLBACK_MODEL='secondary',
                                       _unavailable_until={})
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.init = patch.object(llm_coach, '_ensure_configured')
        self.init.start()
        self.addCleanup(self.init.stop)

    def test_overloaded_primary_uses_secondary_and_cools_down(self):
        operation = MagicMock(side_effect=[Exception('503 private-provider-message'),
                                           MagicMock(text='Helpful reply'), MagicMock(text='Next reply')])
        with self.assertLogs(llm_coach.logger, level='WARNING') as logs:
            self.assertEqual(llm_coach._generate(operation), 'Helpful reply')
        self.assertNotIn('private-provider-message', str(logs.output))
        self.assertEqual(llm_coach._generate(operation), 'Next reply')
        self.assertEqual([call.args[0] for call in operation.call_args_list],
                         ['primary', 'secondary', 'secondary'])

    def test_all_models_down_fail_fast_during_cooldown_then_recover(self):
        operation = MagicMock(side_effect=TimeoutError('private timeout'))
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                llm_coach._generate(operation)
        self.assertEqual(operation.call_count, 2)
        operation.side_effect = None
        operation.return_value.text = 'Recovered'
        with patch.object(llm_coach.time, 'monotonic', return_value=10**20):
            self.assertEqual(llm_coach._generate(operation), 'Recovered')

    def test_tool_side_effect_prevents_model_replay(self):
        operation = MagicMock(side_effect=TimeoutError())
        with self.assertRaises(RuntimeError):
            llm_coach._generate(operation, can_retry=lambda: False)
        self.assertEqual(operation.call_count, 1)

    def test_blank_response_tries_other_model(self):
        operation = MagicMock(side_effect=[MagicMock(text=' '), MagicMock(text='Reply')])
        self.assertEqual(llm_coach._generate(operation), 'Reply')

    def test_chat_does_not_replay_expense_tool_on_second_model(self):
        proposal = MagicMock(return_value={'status': 'awaiting_user_save'})
        def make_model(name, **kwargs):
            def send(*args, **options):
                kwargs['tools'][0](25, 'Food')
                raise TimeoutError('Response interrupted after proposal')
            model = MagicMock()
            model.start_chat.return_value.send_message.side_effect = send
            return model
        sdk = MagicMock()
        sdk.GenerativeModel.side_effect = make_model
        with patch.object(llm_coach, 'genai', sdk), self.assertRaises(RuntimeError):
            llm_coach.chat_reply('Test', 1000, [], 0, 1000, [], [], 'I spent 25 on lunch',
                                 log_expense_fn=proposal)
        proposal.assert_called_once()
        self.assertEqual(sdk.GenerativeModel.call_count, 1)

    def test_recorded_guidance_uses_real_amounts_and_does_not_claim_save(self):
        reply = llm_coach.recorded_guidance('Test', 1000, [], 25, 975,
                                           [{'amount': 25, 'category': 'Food', 'date': '2026-10-01'}],
                                           'What is my biggest expense?')
        self.assertIn('975.00', reply)
        self.assertIn('Food', reply)
        reply = llm_coach.recorded_guidance('Test', 1000, [], message='I spent 25 on lunch')
        self.assertIn('not recorded', reply)
        reply = llm_coach.recorded_guidance('Test', 1000, [], 25, 975,
                                           message='How much have I spent this month?')
        self.assertIn('25.00', reply)
        self.assertNotIn('Add transaction', reply)


if __name__ == '__main__':
    unittest.main()
