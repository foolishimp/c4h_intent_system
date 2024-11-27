Here's my understanding of the agent and skills design:

# Agent Design Core Concepts

1. **BaseAgent**
- Core LLM interaction layer
- Handles provider configuration, model settings
- Provides common process() method for LLM requests
- Manages basic response handling
- Uses configuration from system_config.yml

2. **Agent Implementations**
- Each inherits directly from BaseAgent
- Manages its own prompt templates and modes
- Uses process() directly for LLM interaction
- Examples:
  ```
  SemanticExtractor -> Simple named BaseAgent for extraction tasks
  SemanticIterator -> Handles fast/slow extraction modes
  SolutionDesigner -> Designs code modifications
  Coder -> Implements changes
  ```

3. **Configuration Pattern**
- system_config.yml contains all agent configurations
- Each agent gets its own section with:
  - Provider settings
  - Model selection
  - Temperature
  - Prompt templates

4. **Prompt Management**
- Each agent manages its own prompt templates
- Templates stored in system_config.yml
- Agents format requests using their templates
- No sharing/inheritance of prompts between agents

5. **Processing Flow**
```
Agent
  -> _format_request() using templates
  -> process() from BaseAgent
  -> LLM interaction
  -> Response handling
```

# Key Principles Learned

1. Direct BaseAgent Inheritance
- Agents should inherit directly from BaseAgent
- No intermediate inheritance layers
- Each agent is responsible for its own LLM interaction

2. Configuration Independence
- Each agent manages its own configuration
- No shared/reused configuration between agents
- Cleaner than trying to share extractors/processors

3. Single Responsibility
- Each agent handles one specific type of task
- No attempt to share functionality between agents
- Clean separation of concerns

4. Trust the LLM
- Minimal validation and processing
- Focus on proper prompting
- Let LLM handle the heavy lifting
