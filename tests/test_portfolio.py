"""Tests for bot/portfolio: Mayank's CV answered by rules. Fast: they use the engine, not the runtime."""
import unittest

from bot.portfolio import engine


def ask(text, agent="career", memory=None):
    memory = {} if memory is None else memory
    if agent:
        memory["portfolio_agent"] = agent
    return engine.answer(text, memory), memory


class PortfolioEngineTest(unittest.TestCase):
    def test_named_question_answers_without_portfolio_mode(self):
        reply, _ = ask("who is Mayank?", agent=None)
        self.assertIn("Mayank Ranghadiya", reply)

    def test_unrelated_line_is_left_to_pybot(self):
        self.assertIsNone(ask("how do i boil an egg", agent=None)[0])
        self.assertIsNone(ask("tell me a joke")[0])

    def test_skill_known_and_gap(self):
        self.assertIn("Celery", ask("does he know celery?")[0])
        reply, memory = ask("has he worked with java?")
        self.assertIn("isn't on", reply)
        self.assertEqual(memory["portfolio_last"], "skill:Java")

    def test_company_and_follow_up(self):
        memory = {}
        first, _ = ask("tell me about crest data", memory=memory)
        more, _ = ask("tell me more", memory=memory)
        self.assertIn("Crest Data", first)
        self.assertIn("More from **Crest Data**", more)
        self.assertNotEqual(first, more)

    def test_job_fit(self):
        jd = ("We are looking for a Senior Backend Engineer with 5+ years of Python. You will build distributed "
              "systems with Celery, Kafka and Redis on AWS and REST APIs in FastAPI. Terraform is a plus.")
        reply, memory = ask(jd)
        self.assertEqual(memory["portfolio_last"], "fit")
        self.assertIn("fit", reply.splitlines()[0].lower())
        self.assertIn("Kafka", reply)
        self.assertIn("Terraform", reply)

    def test_never_invents_unknowns(self):
        self.assertIn("isn't in", ask("what does he think about cricket?")[0])
        self.assertIn("aren't something I can answer", ask("what is his notice period?")[0])

    def test_suggestions(self):
        _, memory = ask("what services do you offer?", agent="client")
        self.assertTrue(1 <= len(memory["portfolio_suggestions"]) <= 3)

    def test_every_agent_greets(self):
        for key in engine.AGENTS:
            self.assertIn(engine.AGENTS[key][0], ask("hi", agent=key)[0])


if __name__ == "__main__":
    unittest.main()
