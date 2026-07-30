import os
from pathlib import Path
from anthropic import Anthropic
from lib.ai_generation import MessageList


PROMPT = """
Generate an evaluation dataset for a prompt evaluation. The dataset will be used to evaluate prompts that generate Python, JSON, or Regex specifically for AWS-related tasks. Generate an array of JSON objects, each representing task that requires Python, JSON, or a Regex to complete.

Example output:

```json
[
  {
    "task": "Description of task",
  },
  ...additional
]
```

* Focus on tasks that can be solved by writing a single Python function, a single JSON object, or a single regex
* Focus on tasks that do not require writing much code

Please generate 10 objects.
"""


def generate_dataset() -> str:
    client = Anthropic()

    message_list = MessageList()
    message_list.add_user_message(PROMPT)
    message_list.add_assistant_message("[{")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        messages=message_list,
        max_tokens=20000,
        stop_sequences=[
            "}]",
            "}\n]",
            "}\n  ]",
            "}\n    ]"
        ]
    )

    return "[{" + response.content[0].text + "}]"

def main() -> None:
    dirname = os.path.dirname(__file__)
    output_path = Path(dirname) / "dataset.data.json"

    with open(output_path, "w") as f:
        f.write(generate_dataset())


if __name__ == "__main__":
    main()