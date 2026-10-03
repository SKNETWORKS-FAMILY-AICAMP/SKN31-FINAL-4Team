import json
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values
from openai import OpenAI

def load_agent_environment():
    """Find project .env from this module, independent of terminal working directory."""
    explicit = os.environ.get('FEEDIT_ENV_PATH')
    candidates = [Path(explicit)] if explicit else [Path(__file__).resolve().parents[3] / '.env', Path(__file__).resolve().parents[2] / '.env']
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            values = dotenv_values(path)
            for key in ('OPENAI_API_KEY','FEEDIT_PRODUCT_AGENT_MODEL','OPENAI_MODEL'):
                if not os.environ.get(key, '').strip() and values.get(key):
                    os.environ[key] = values[key]
            return str(path)
    return None


class OpenAIReviewer:
    """One client shared by bounded review threads; no DB/tools exposed to model."""
    def __init__(self, *, model=None, client=None, timeout=90, max_output_tokens=6000):
        self.env_path = load_agent_environment()
        self.model = model or os.environ.get('FEEDIT_PRODUCT_AGENT_MODEL') or os.environ.get('OPENAI_MODEL')
        if not self.model:
            raise ValueError('Set FEEDIT_PRODUCT_AGENT_MODEL or OPENAI_MODEL to a structured-output GPT model.')
        if client is None and not os.environ.get('OPENAI_API_KEY', '').strip():
            raise ValueError(f'OPENAI_API_KEY is missing. Loaded .env: {self.env_path}. Set FEEDIT_ENV_PATH to the project .env path.')
        self.client = client or OpenAI(timeout=timeout, max_retries=2)
        self.max_output_tokens = max_output_tokens

    def review(self, *, role, prompt, payload, schema):
        response = self.client.responses.parse(
            model=self.model,
            input=[{'role':'system', 'content':prompt},
                   {'role':'user', 'content':json.dumps(payload, ensure_ascii=False, default=str)}],
            text_format=schema, store=False, max_output_tokens=self.max_output_tokens,
        )
        if response.status != 'completed' or response.output_parsed is None:
            raise RuntimeError(f'{role}: response incomplete or refused ({response.status})')
        parsed = response.output_parsed
        usage = getattr(response, 'usage', None)
        if usage is not None:
            parsed._usage = {
                'input_tokens': usage.input_tokens,
                'output_tokens': usage.output_tokens,
                'total_tokens': usage.total_tokens,
                'reasoning_tokens': getattr(getattr(usage, 'output_tokens_details', None), 'reasoning_tokens', None),
            }
        return parsed
