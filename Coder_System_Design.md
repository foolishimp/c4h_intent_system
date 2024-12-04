# Coder System Design

## Overview
Coder is an LLM-based code refactoring system using semantic operators to process and apply code changes.

## Core Components

```mermaid
classDiagram
    class Coder {
        +process_refactor(solution: str)
        -apply_changes(changes: List[Change])
    }
    
    class SemanticExtract {
        +extract(content: str, prompt: str): ExtractResult
        -_format_request(context: Dict)
    }
    
    class SemanticIterator {
        +iter_extract(content: Any, config: ExtractConfig): ItemIterator
        -LIST_FORMAT_PROMPT: str
    }
    
    class SemanticMerge {
        +merge(original: str, changes: List[Change]): str
        -apply_diff(source: str, diff: str)
    }
    
    class ItemIterator {
        +has_next(): bool
        +__next__(): Any
    }

    Coder --> SemanticExtract
    Coder --> SemanticIterator
    Coder --> SemanticMerge
    SemanticIterator --> ItemIterator

```

## Process Flow

```mermaid
sequenceDiagram
    participant C as Coder
    participant E as SemanticExtract
    participant I as SemanticIterator
    participant M as SemanticMerge
    
    C->>E: Extract refactor actions
    E-->>C: Structured changes
    C->>I: Create iterator
    loop For each change
        I->>C: Next change
        C->>M: Apply change
        M-->>C: Updated code
    end
```

## Key Principles

1. LLM-First Processing
   - Minimal validation
   - Trust LLM output
   - Focus on infrastructure

2. Component Responsibilities
   - Extract: Parse solution into changes
   - Iterator: Process changes sequentially 
   - Merge: Apply changes to code

3. Data Flow
   - Solution Design → Changes List → Applied Changes

## Implementation Notes
- Uses inline prompts for extraction
- No cross-validation between components
- Maintains original content structure
- Handles both structured/unstructured input

# Semantic Iterator Design

## Core Components

1. **SemanticPrompt**
   - Instruction pattern to match
   - Expected output format (default: json)

2. **SemanticList[T]**
   - Generic container for extracted items
   - Provides length, indexing, iteration

3. **SemanticIterator[T]**
   - Async iterator implementation
   - Uses SemanticExtract for LLM-based extraction
   - Supports direct dictionary input

## Operation Flow

1. Iterator instantiated with:
   ```python
   SemanticIterator(config, content, prompt)
   ```

2. First `await iter` triggers:
   - Checks for direct item access (`changes`, `items`, `results`)
   - Otherwise extracts via LLM using prompt
   - Populates internal SemanticList

3. Iteration:
   ```python 
   async for item in iterator:
      process(item)
   ```

## Response Handling

- Direct dictionary -> List mapping
- Raw LLM output parsing
- Dict to key-value conversion 
- Error state returns empty list

## Usage Example
```python
iterator = SemanticIterator(
    config=llm_config,
    content=source_text,
    prompt=SemanticPrompt("Extract each {item} with fields...")
)
async for item in iterator:
    process(item)
```

### Additional Notes

Problem Space:
- Working with semantic iterator and extract for parsing structured data
- Test suite revealing issues with response handling
- Testing framework configuration challenges

Components at Play:

Semantic Iterator
Core Principles:
Acts as a list processor over semantic extractions
Works with BaseAgent for LLM interactions
Handles parsing and validation of responses
Provides iterator interface for extracted items

Semantic Extract (BaseAgent)
Key Functions:
Makes LLM API calls
Wraps responses in raw_output field
Handles retries and errors
Requires provider configuration and API keys
Key Issues Found:
1. Configuration Chain:

SemanticIterator -> SemanticExtract -> BaseAgent -> LiteLLM

- Missing env_var in config
- Authentication setup incomplete

```python
Response Structure: python
Response = {
 'raw_output': [  # Wrapper from BaseAgent
     {'name': 'DataProcessor', 'code': '...'}, 
     # More items...
 ]
}
```

LLM returns correct structure
Parser fails due to raw_output wrapper
Need to handle nested response format

Infrastructure:
Event loop management in tests
Fixture scoping and ordering
API key mocking
Main Learning Points:
1. Semantic iterator expects unwrapped JSON array responses
2. BaseAgent adds response wrapping we need to handle
3. Configuration needs complete provider setup including env vars
4. Test infrastructure needs proper async and mock setup

Next Steps Would Be:
1. Fix config structure
2. Handle response unwrapping 
3. Sort out test infrastructure
4. Then focus on parsing improvements

### More Design Notes
```mermaid
classDiagram
    class BaseAgent {
        <<abstract>>
        +provider: LLMProvider
        +model: str
        +temperature: float
        +config: Dict
        +process(intent: Dict) AgentResponse
        #_create_standard_response()
        #_format_request()
        #_parse_response()
    }

    class Coder {
        +merger: SemanticMerge
        +iterator: SemanticIterator
        +process(context: Dict) AgentResponse
        +transform(context: Dict) TransformResult
        -_backup_file(path: Path) Path
    }

    class SemanticMerge {
        +merge(original: str, changes: str) MergeResult
        -_extract_code_content(response: Dict) str
        -_validate_code(content: str) bool
    }

    class SemanticIterator {
        +iter_extract(content: Any, config: ExtractConfig) ItemIterator
        -_extract_items(data: Any) List
        -_validate_items(items: List) bool
    }

    class TransformResult {
        +success: bool
        +file_path: str
        +backup_path: str
        +error: str
    }

    class AgentResponse {
        +success: bool
        +data: Dict
        +error: str
    }

    class ItemIterator~T~ {
        +has_next() bool
        +next() T
        +peek() T
        +back() T
        +reset()
        +skip(count: int)
    }

    BaseAgent <|-- Coder
    BaseAgent <|-- SemanticMerge
    Coder --> SemanticMerge
    Coder --> SemanticIterator
    Coder ..> TransformResult
    Coder ..> AgentResponse
    SemanticIterator ..> ItemIterator
```

```mermaid
stateDiagram-v2
    [*] --> RequestReceived: Transform Request
    
    RequestReceived --> ValidationPhase: Parse Request
    ValidationPhase --> BackupPhase: Valid Request
    ValidationPhase --> Error: Invalid Request
    
    BackupPhase --> ExtractionPhase: Backup Created
    BackupPhase --> Error: Backup Failed
    
    state ExtractionPhase {
        [*] --> ExtractChanges
        ExtractChanges --> ValidateChanges
        ValidateChanges --> ProcessChanges: Valid
        ValidateChanges --> ExtractError: Invalid
        ProcessChanges --> [*]: Success
        ProcessChanges --> ExtractError: Failure
    }
    
    ExtractionPhase --> MergePhase: Changes Extracted
    ExtractionPhase --> Error: Extraction Failed
    
    state MergePhase {
        [*] --> MergeChanges
        MergeChanges --> ValidateMerge
        ValidateMerge --> WriteMerge: Valid
        ValidateMerge --> MergeError: Invalid
        WriteMerge --> [*]: Success
        WriteMerge --> MergeError: Write Failed
    }
    
    MergePhase --> Success: Changes Applied
    MergePhase --> Error: Merge Failed
    
    Error --> RestoreBackup: Has Backup
    Error --> [*]: No Backup
    
    RestoreBackup --> [*]
    Success --> [*]
```