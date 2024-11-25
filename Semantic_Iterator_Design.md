Here's the key design principles of each component:

```mermaid
classDiagram
    class SemanticIterator {
        Principles
        - Iteration Interface Expert
        - Mode Manager
        - Knows Nothing About Content
        - Same Interface Both Modes
        
        Responsibilities
        + Manages extraction modes
        + Provides iteration patterns
        + Handles state tracking
        + Returns structured items
    }

    class SemanticExtractor {
        Principles
        - Raw Extraction Expert
        - Content Agnostic
        - Single Responsibility
        - Returns Raw Responses
        
        Responsibilities
        + Formats extraction prompts
        + Makes LLM calls
        + Returns raw results
        + No structure enforcement
    }

    class FastMode {
        Principles
        - Optimize for Speed
        - Single Shot Extraction
        - Pre-extract Everything
        
        Operation
        1. Try direct JSON parse
        2. Single LLM call if needed
        3. Return complete list
        4. Simple list iteration
    }

    class SlowMode {
        Principles
        - Optimize for Accuracy
        - Item by Item Extraction
        - Semantic Position Count
        
        Operation
        1. Initialize position counter
        2. Extract Nth item on demand
        3. Use semantic positioning
        4. Stop on NO_MORE_ITEMS
    }

    SemanticIterator --> FastMode
    SemanticIterator --> SlowMode
    SemanticIterator --> SemanticExtractor

```

1. SemanticIterator
   - Pure iteration expert
   - Knows nothing about content meaning
   - Provides consistent interface for both modes
   - Manages extraction state and modes
   - Simple principle: "I know how to iterate over things"

2. SemanticExtractor
   - Pure extraction expert
   - Single responsibility: get content from LLM
   - Returns raw responses
   - No understanding of structure required
   - Simple principle: "I know how to ask LLM for things"

3. Fast Mode
   - Optimized for when content can be returned as list
   - Pre-extracts everything in one shot
   - Simple list-based iteration
   - Good when LLM can return structured list
   - Simple principle: "Give me everything as a list"

4. Slow Mode
   - Uses semantic positioning for extraction
   - No list maintenance - just a counter
   - Leverages LLM's understanding of "next item"
   - Better for complex content patterns
   - Simple principle: "Give me the Nth item"

Key Design Principles:
1. Clear Separation of Concerns:
   - Iterator: manages iteration
   - Extractor: handles LLM interaction
   - Modes: define extraction patterns

2. Simple Interface:
   ```python
   iterator = SemanticIterator(config, mode='fast')
   async for item in iterator.iter_extract(content, config):
       process(item)
   ```

3. Mode Independence:
   - Same interface regardless of mode
   - Different internal strategies
   - No mode mixing unless explicitly configured

4. Content Agnostic:
   - Iterator doesn't need to understand content
   - Extractor doesn't need to understand structure
   - LLM handles semantic understanding

Would you like me to:
1. Show specific examples of these principles in action?
2. Elaborate on any particular principle?
3. Show how these principles guide error handling?