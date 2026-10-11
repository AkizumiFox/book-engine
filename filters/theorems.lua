--[[
Theorems Lua Filter for Pandoc
==============================
Handles theorem-like environments, cross-references, and counters.
Also handles numbered equations with {#eq-id} syntax.

Features:
- Parses Quarto-style fenced divs: ::: {#thm-name} ... :::
- Parses display math with IDs: $$ ... $${#eq-name}
- Manages multi-level counters (chapter.section.serial)
- Resolves cross-references: @thm-name, @eq-name -> linked text
- Generates HTML div or LaTeX environment based on output format
- Preserves math notation in titles

Part of the book engine (see BUILD.md).
]]

-- =============================================================================
-- Configuration
-- =============================================================================

-- Environment types and their display names
local ENVIRONMENT_NAMES = {
    ["equation"] = "Eq."
}

-- Environments that share a counter (map of env -> shared_counter_name)
-- e.g. { theorem = "main", lemma = "main" }
local SHARED_COUNTER_MAPPING = {}

-- Track which environments are numbered
local NUMBERED_ENVS = {
    ["equation"] = true
}

-- "Big" environments (block style with separate title) vs "Small" (inline title)
-- Map of "env_name" -> "big" or "small"
local ENV_STYLES = {}

-- Map of "env_name" -> {border = "#..."} (the stylesheet derives tints from it)
local ENV_COLORS = {}

-- ID prefix to environment type mapping (Quarto-style)
-- e.g. { ["thm"] = "theorem" }
local ID_PREFIX_MAP = {
    ["eq"] = "equation"
}

-- =============================================================================
-- State Management
-- =============================================================================

-- Counter state
local counters = {
    shared = 0,           -- Shared counter for theorem-like envs
    independent = {},     -- {env_type: counter_value}
    chapter = 0,
    section = 0,
    equation = 0,         -- Explicit equation counter
}

-- Label registry for cross-references
local labels = {}

-- Document meta (set in Pandoc handler, used in render)
local doc_meta = nil

-- Tooltip data shard for labels defined in the current document
local function page_shard()
    return doc_meta and doc_meta["page-shard"] and pandoc.utils.stringify(doc_meta["page-shard"]) or ""
end

local function is_book_mode()
    return doc_meta and doc_meta["book-mode"] and pandoc.utils.stringify(doc_meta["book-mode"]) == "true"
end

-- Processed environments registry (to pass data between filter passes)
local processed_envs = {}

-- Keys of theorem divs that are nested inside another small env (for LaTeX: use non-framed variant)
local nested_div_keys = {}

-- Book mode: current file's chapter/section (updated by file-boundary divs)
local current_file_chapter = 0
local current_file_section = 0
local current_file_is_preface = false  -- True only for src/index.md (actual preface)
local last_book_part = -2  -- Only emit \setcounter/\part when part changes (fixes ch00 numbering)

-- Initialize environments from metadata
local function init_environments(meta)
    if not meta.environment_settings then return end
    
    local settings = meta.environment_settings
    
    -- Load Big Envs
    if settings.big_envs then
        for _, env in ipairs(settings.big_envs) do
            local prefix = pandoc.utils.stringify(env.prefix)
            local name = pandoc.utils.stringify(env.name)
            local shared = env.counter_group and pandoc.utils.stringify(env.counter_group)
            local color = env.color and pandoc.utils.stringify(env.color)
            
            -- Handle boolean numbered
            local numbered = true
            if env.numbered == false then numbered = false end
            
            -- Register
            -- We use the name (lowercase) as the internal key if possible, or prefix
            local key = name:lower():gsub("%s+", "-")
            
            -- Map prefix to key
            ID_PREFIX_MAP[prefix] = key
            
            -- Register display name
            ENVIRONMENT_NAMES[key] = name
            
            -- Register styling
            ENV_STYLES[key] = "big"
            
            -- Register colors if present
            if color ~= "nil" and color ~= "" then
                ENV_COLORS[key] = { border = color }
            end
            
            -- Register shared counter
            if shared and shared ~= "" and shared ~= "nil" then
                SHARED_COUNTER_MAPPING[key] = shared
            end
            
            -- Register numbered status
            if numbered then
                NUMBERED_ENVS[key] = true
            end
        end
    end
    
    -- Load Small Envs
    if settings.small_envs then
        -- Display name overrides for multi-word environments
        local display_overrides = {
            proofofclaim = "Proof of Claim",
            check = "Quick check",
        }
        
        for _, env_name in ipairs(settings.small_envs) do
            local key = pandoc.utils.stringify(env_name):lower()
            local name = pandoc.utils.stringify(env_name)
            
            -- Use override if available, otherwise capitalize first letter
            local display_name = display_overrides[key] or key:gsub("^%l", string.upper)
            
            ENVIRONMENT_NAMES[key] = display_name
            ENV_STYLES[key] = "small"
            
            -- Small envs are unnumbered by default based on spec
            -- so we don't add to NUMBERED_ENVS
        end
    end
end

-- Get chapter/section from metadata
local function init_counters(meta)
    -- Initialize environments first
    init_environments(meta)

    local function parse_meta_num(val)
        if not val then return 0 end
        if type(val) == "string" or type(val) == "number" then
            return tonumber(val) or 0
        elseif type(val) == "table" and val.t == "MetaInlines" then
            return tonumber(pandoc.utils.stringify(val)) or 0
        elseif type(val) == "table" and val.t == "MetaString" then
            return tonumber(val.c) or 0
        else
            -- final fallback
            return tonumber(pandoc.utils.stringify(val)) or 0
        end
    end

    -- Try both formats
    local c_num = meta["chapter-num"] or meta["chapter_num"]
    local s_num = meta["section-num"] or meta["section_num"]

    counters.chapter = parse_meta_num(c_num)
    counters.section = parse_meta_num(s_num)
    
    -- Reset counters for each file
    counters.shared = {} -- Map of shared_counter_name -> value
    counters.independent = {}
    counters.equation = 0
end

-- Format counter as chapter.section.serial (3-level)
local function format_counter(counter)
    return string.format("%d.%d.%d", counters.chapter, counters.section, counter)
end

-- Get next number for an environment type
local function get_next_number(env_type)
    if not NUMBERED_ENVS[env_type] then return nil end
    
    if env_type == "equation" then
        counters.equation = counters.equation + 1
        return format_counter(counters.equation)
    end
    
    local shared_name = SHARED_COUNTER_MAPPING[env_type]
    if shared_name then
        counters.shared[shared_name] = (counters.shared[shared_name] or 0) + 1
        return format_counter(counters.shared[shared_name])
    else
        counters.independent[env_type] = (counters.independent[env_type] or 0) + 1
        return format_counter(counters.independent[env_type])
    end
end

-- Stable per-document key for an environment div, stored as an attribute so it survives
-- between filter passes. (tostring(div) collided for identical unlabeled environments.)
local next_env_key = 0
local function get_div_key(div)
    local key = div.attributes["data-env-key"]
    if not key then
        next_env_key = next_env_key + 1
        key = tostring(next_env_key)
        div.attributes["data-env-key"] = key
    end
    return key
end

-- Render inlines to a string in the given format (for cross-reference text)
local function inlines_to(format, inlines)
    if not inlines or #inlines == 0 then return "" end
    local ok, out = pcall(pandoc.write, pandoc.Pandoc({pandoc.Plain(inlines)}), format,
        {html_math_method = "mathjax"})
    if not ok then return pandoc.utils.stringify(pandoc.Inlines(inlines)) end
    return (out:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- Label metadata shared by scan mode and the in-document registry
local function label_record(env_type, number, title_inlines)
    return {
        type = env_type,
        type_name = ENVIRONMENT_NAMES[env_type] or env_type,
        number = number or "",
        title = title_inlines and pandoc.utils.stringify(pandoc.Inlines(title_inlines)) or "",
        title_html = inlines_to("html", title_inlines),
        title_latex = inlines_to("latex", title_inlines),
    }
end

-- =============================================================================
-- Environment Detection
-- =============================================================================

-- Extract environment type from div classes OR ID prefix
local function get_env_type(div)
    -- First, check classes (for small envs like .remark)
    for _, class in ipairs(div.classes) do
        if ENVIRONMENT_NAMES[class] then
            return class
        end
    end
    
    -- Second, check ID prefix (Quarto-style like #thm-name)
    local id = div.identifier or ""
    if id ~= "" then
        local prefix = id:match("^(%w+)%-")
        -- Check dynamic map
        if prefix and ID_PREFIX_MAP[prefix] then
            return ID_PREFIX_MAP[prefix]
        end
    end
    
    return nil
end

-- Extract label ID from div attributes (e.g., id="thm-pythagorean")
local function get_label_id(div)
    return div.identifier
end

-- `::: {#thm-foo .optional}` marks a result that is worth stating and proving but that
-- no reader is obliged to read: an illustration, or a bridge to another part of the
-- book. The class is recorded on the label (scan_and_dump_labels), printed as a marker
-- in both editions, and enforced -- nothing anywhere may prove anything from an optional
-- result, which tools/check_optional.py checks and ./build.py check fails on.
local OPTIONAL_CLASS = "optional"

-- What the marker says. One sentence, both halves of the promise: the reader may skip
-- it, and skipping it costs nothing later.
local OPTIONAL_NOTE = "Optional: nothing later depends on this."

local function is_optional(div)
    for _, class in ipairs(div.classes or {}) do
        if class == OPTIONAL_CLASS then return true end
    end
    return false
end

-- Extract title from first element in div (if any)
local function extract_title(div)
    if #div.content == 0 then return nil end
    
    local first_block = div.content[1]
    
    -- Check for Header (## Title)
    if first_block.t == "Header" then
        local title_inlines = first_block.content
        table.remove(div.content, 1)
        return title_inlines
    end
    
    -- Check for Para with title syntax
    if first_block.t == "Para" and #first_block.content >= 1 then
        local content = first_block.content
        local first_inline = content[1]
        
        -- Case 1: [Title]{} -> Span element (first element is a Span)
        if first_inline.t == "Span" then
            local title_inlines = first_inline.content
            table.remove(content, 1)
            
            -- Cleanup following whitespace/softbreak
            while #content > 0 do
                local next_inline = content[1]
                if next_inline.t == "Space" or next_inline.t == "SoftBreak" then
                    table.remove(content, 1)
                else
                    break
                end
            end
            
            -- If paragraph is empty, remove it
            if #content == 0 then
                table.remove(div.content, 1)
            end
            
            return title_inlines
        end
        
        -- Case 2: [Title]() -> Link element with empty URL
        if first_inline.t == "Link" then
            local title_inlines = first_inline.content
            table.remove(content, 1)
            
            -- Cleanup following whitespace/softbreak
            while #content > 0 do
                local next_inline = content[1]
                if next_inline.t == "Space" or next_inline.t == "SoftBreak" then
                    table.remove(content, 1)
                else
                    break
                end
            end
            
            -- If paragraph is empty, remove it
            if #content == 0 then
                table.remove(div.content, 1)
            end
            
            return title_inlines
        end
        
        -- Case 3: [Title] as plain text (Str starting with [)
        local first_str = pandoc.utils.stringify(first_inline)
        if first_str:sub(1, 1) == "[" then
            -- Scan for closing ]
            local end_index = nil
            
            for i, inline in ipairs(content) do
                if inline.t == "Str" and inline.text:match("%]$") then
                    end_index = i
                    break
                end
            end
            
            if end_index then
                local title_inlines = {}
                
                -- Extract title content
                for i = 1, end_index do
                    local inline = content[i]
                    local title_element = inline
                    
                    -- Handle leading [
                    if title_element.t == "Str" and i == 1 and title_element.text:sub(1, 1) == "[" then
                        local text = title_element.text:sub(2)
                        title_element = pandoc.Str(text)
                    end
                    
                    -- Handle trailing ]
                    if title_element.t == "Str" and i == end_index and title_element.text:sub(-1) == "]" then
                        local text = title_element.text:sub(1, -2)
                        title_element = pandoc.Str(text)
                    end
                    
                    -- Insert if not empty
                    if title_element.t == "Str" and title_element.text == "" then
                        -- Skip empty strings
                    else
                        table.insert(title_inlines, title_element)
                    end
                end
                
                -- Remove title elements from paragraph
                for i = 1, end_index do
                    table.remove(content, 1)
                end
                
                -- Cleanup following whitespace/softbreak
                while #content > 0 do
                    local next_inline = content[1]
                    if next_inline.t == "Space" or next_inline.t == "SoftBreak" then
                        table.remove(content, 1)
                    else
                        break
                    end
                end
                
                -- If paragraph is empty, remove it
                if #content == 0 then
                    table.remove(div.content, 1)
                end
                
                return title_inlines
            end
        end
    end
    
    return nil
end

-- =============================================================================
-- Equation Processing
-- =============================================================================

-- A tagged display may share its paragraph with ordinary prose, as in
-- "... so normality says \[ ... \]{#eq-foo}". Returning only the equation would
-- silently drop that prose from both HTML and PDF, so keep whatever sits on either
-- side of the display as its own paragraph.
local function with_surrounding_text(para, math_index, id_index, equation_block)
    local function trim(inlines)
        while #inlines > 0 and (inlines[1].t == "Space" or inlines[1].t == "SoftBreak") do
            table.remove(inlines, 1)
        end
        while #inlines > 0 and (inlines[#inlines].t == "Space" or inlines[#inlines].t == "SoftBreak") do
            table.remove(inlines)
        end
        return inlines
    end

    local before, after = {}, {}
    for i = 1, math_index - 1 do table.insert(before, para.content[i]) end
    for i = (id_index or math_index) + 1, #para.content do table.insert(after, para.content[i]) end
    trim(before)
    trim(after)

    local blocks = {}
    if #before > 0 then table.insert(blocks, pandoc.Para(before)) end
    table.insert(blocks, equation_block)
    if #after > 0 then table.insert(blocks, pandoc.Para(after)) end
    return blocks
end

local function process_para_math(para, mode)
    local found_math = nil
    local found_id = nil
    local math_index = nil
    local id_index = nil
    
    for i, el in ipairs(para.content) do
        if el.t == "Math" and el.mathtype == "DisplayMath" then
            found_math = el
            math_index = i
            
            -- Look ahead for ID
            for j = i + 1, #para.content do
                local next_el = para.content[j]
                if next_el.t == "Str" and next_el.text:match("^{#eq%-[%w%-]+}$") then
                    found_id = next_el.text:match("^{#(eq%-[%w%-]+)}$")
                    id_index = j
                    break
                elseif next_el.t ~= "Space" and next_el.t ~= "SoftBreak" then
                    break -- sequence broken
                end
            end
            
            if found_id then break end
        end
    end

    if found_math and found_id then
        if mode == "collect" then
             local number = get_next_number("equation")
             local key = found_id
             
             -- Store in registry
             processed_envs[key] = {
                 number = number,
                 math = found_math
             }
             
             labels[found_id] = label_record("equation", number, nil)
             return nil
             
        elseif mode == "render" then
             local key = found_id
             local info = processed_envs[key]
             if not info then return nil end
             
             local number = info.number
             local math_content = found_math.text
             
             if FORMAT:match("html") then
                 -- Construct AST for HTML output
                 
                 -- Math Block
                 -- We want the math to be display math.
                 local math_el = pandoc.Math("DisplayMath", math_content)
                 
                 -- Container Divs
                 -- Outer Div (flex container)
                 --   Inner Div 1 (Math, centered, grow)
                 --   Inner Div 2 (Number, right, fixed)
                 
                 local math_container = pandoc.Div(
                    {pandoc.Plain({math_el})}, 
                    pandoc.Attr("", {}, {style="flex-grow: 1; text-align: center;"})
                 )
                 
                 local number_container = pandoc.Div(
                    {pandoc.Plain({pandoc.Str("(" .. number .. ")")})},
                    pandoc.Attr("", {}, {style="flex-shrink: 0; margin-left: 1em;"})
                 )
                 
                 local outer_div = pandoc.Div(
                    {math_container, number_container},
                    pandoc.Attr(found_id, {"equation"}, {style="display: flex; align-items: center; width: 100%; margin: 1em 0;"})
                 )
                 
                 return with_surrounding_text(para, math_index, id_index, outer_div)
                 
             elseif FORMAT:match("latex") then
                 -- \label must follow the body: directly after \begin{equation} it picks up
                 -- the section number instead of the equation number.
                 -- Blank lines inside the body would be paragraph breaks in math mode.
                 local body = math_content:gsub("^%s+", ""):gsub("%s+$", ""):gsub("\n%s*\n", "\n")
                 local tex = string.format("\\begin{equation}\n%s\n\\label{%s}\n\\end{equation}", body, found_id)
                 return with_surrounding_text(para, math_index, id_index, pandoc.RawBlock("latex", tex))
             else
                 -- For other formats, try to do something reasonable or leave as is
                 return nil
             end
        elseif mode == "scan" then
             local number = get_next_number("equation")
             
             -- Construct AST for MathJax-friendly HTML output
             local math_el = pandoc.Math("DisplayMath", found_math.text)
             local doc = pandoc.Pandoc({pandoc.Para({math_el})})
             
             local status, html_preview = pcall(pandoc.write, doc, 'html', {html_math_method = 'mathjax'})
             
             if not status then
                 -- Fallback to raw tex if something goes wrong
                 html_preview = string.format("$$ %s $$", found_math.text)
             end

             return {
                 id = found_id,
                 type = "equation",
                 type_name = "Eq.",
                 number = number,
                 title = "",
                 html_content = html_preview
             }
        end
    end
    return nil
end

-- =============================================================================
-- HTML Output (Theorems)
-- =============================================================================

local function render_env_html(env_type, number, title_inlines, label_id, content, optional)
    local display_name = ENVIRONMENT_NAMES[env_type] or env_type
    local style = ENV_STYLES[env_type] or "big"
    
    if style == "small" then
        -- Small Env: Inline title
        -- Format: *Name.* or *Name (Title).* Content...
        local title_content = {}
        
        -- Name (italic)
        table.insert(title_content, pandoc.Emph({pandoc.Str(display_name)}))
        
        -- Title
        if title_inlines and #title_inlines > 0 then
            table.insert(title_content, pandoc.Space())
            table.insert(title_content, pandoc.Str("("))
            for _, inline in ipairs(title_inlines) do
                table.insert(title_content, inline)
            end
            table.insert(title_content, pandoc.Str(")"))
        end
        
        -- Period and space (italic period)
        table.insert(title_content, pandoc.Emph({pandoc.Str(".")}))
        table.insert(title_content, pandoc.Space())
        
        -- Prepend to content
        if #content > 0 and content[1].t == "Para" then
            -- Prepend to existing first paragraph
            for i = #title_content, 1, -1 do
                table.insert(content[1].content, 1, title_content[i])
            end
        else
            -- Create new paragraph
            table.insert(content, 1, pandoc.Para(title_content))
        end
        
        local classes = {env_type, "small-env"}
        if optional then table.insert(classes, OPTIONAL_CLASS) end
        local attrs = pandoc.Attr(
            label_id or "",
            classes,
            {["data-env-type"] = env_type}
        )
        return pandoc.Div(content, attrs)
        
    else
        -- Big Env: Block title
        -- Build title content as list of inlines
        local title_content = {}
        table.insert(title_content, pandoc.Strong(pandoc.Str(display_name)))
        if number then
            table.insert(title_content, pandoc.Strong(pandoc.Str(" " .. number)))
        end
        if title_inlines and #title_inlines > 0 then
            table.insert(title_content, pandoc.Str(" ("))
            for _, inline in ipairs(title_inlines) do
                table.insert(title_content, inline)
            end
            table.insert(title_content, pandoc.Str(")"))
        end
        
        -- The optional marker rides on the title line, after the name and the number:
        -- the reader meets it exactly where they decide whether to read on.
        if optional then
            table.insert(title_content, pandoc.Space())
            table.insert(title_content, pandoc.Span(
                {pandoc.Str(OPTIONAL_NOTE)},
                pandoc.Attr("", {"env-optional"})
            ))
        end

        -- Create the title span
        local title_span = pandoc.Span(
            title_content,
            pandoc.Attr("", {"theorem-title", "theorem-title-resolved"})
        )
        
        -- A list of pairs (not a table keyed by name) keeps attribute order stable between builds
        local attributes = {
            {"data-env-type", env_type},
            {"data-number", number or ""},
        }
        
        -- The environment's color from the config; the stylesheet derives the rule and
        -- the background tint from it (for light and dark mode)
        local colors = ENV_COLORS[env_type]
        if colors and colors.border then
            table.insert(attributes, {"style", "--env-color: " .. colors.border})
        end
        
        local classes = {env_type, "env"}
        if optional then table.insert(classes, OPTIONAL_CLASS) end

        local attrs = pandoc.Attr(
            label_id or "",
            classes,
            attributes
        )
        
        -- Insert title at beginning
        table.insert(content, 1, pandoc.Plain({title_span}))
        
        return pandoc.Div(content, attrs)
    end
end

-- =============================================================================
-- LaTeX Output (Theorems)
-- =============================================================================

-- Map small env types to their "inline" LaTeX env (title in content, not in env)
local SMALL_ENV_INLINE = {
    remark = "remarkinline",
    solution = "solutioninline",
    claim = "claiminline",
    proof = "proofinline",
    proofofclaim = "proofinline",
    idea = "ideainline",
    warning = "warninginline",
    check = "checkinline",
    algorithm = "algorithminline",
}
-- Nested variants (no mdframed box) for claim/proof inside another small env
local SMALL_ENV_NESTED = {
    claim = "claimnested",
    proof = "proofnested",
    proofofclaim = "proofnested",
}

local function render_env_latex(env_type, number, title_inlines, label_id, content, is_nested, optional)
    local c, s
    if doc_meta and doc_meta["book-mode"] and pandoc.utils.stringify(doc_meta["book-mode"]) == "true" then
        c = current_file_chapter
        s = current_file_section
    else
        c = doc_meta and (tonumber(pandoc.utils.stringify(doc_meta["chapter-num"] or 0)) or 0) or 0
        s = doc_meta and (tonumber(pandoc.utils.stringify(doc_meta["section-num"] or 0)) or 0) or 0
    end
    -- Only actual preface (src/index.md) gets unnumbered; ch00 (prerequisites) gets numbered 0.x.y
    local is_preface
    if doc_meta and doc_meta["book-mode"] and pandoc.utils.stringify(doc_meta["book-mode"]) == "true" then
        is_preface = current_file_is_preface
    else
        is_preface = doc_meta and pandoc.utils.stringify(doc_meta["is-preface"] or "") == "true"
    end
    local latex_env = env_type
    if is_preface and (NUMBERED_ENVS[env_type] or SHARED_COUNTER_MAPPING[env_type]) then
        latex_env = env_type .. "*"
    end
    local display_name = ENVIRONMENT_NAMES[env_type] or env_type
    local style = ENV_STYLES[env_type] or "big"
    
    -- For small envs: prepend title to first block so "Remark. For other examples..."
    -- flows inline without paragraph break. Use inline env variant (no title in def).
    -- When nested inside another small env, use nested variant (no mdframed) to avoid LaTeX nesting limits.
    local use_nested = is_nested and (SMALL_ENV_NESTED[env_type] ~= nil)
    local nested_env = use_nested and SMALL_ENV_NESTED[env_type] or nil
    local use_inline = (style == "small") and (SMALL_ENV_INLINE[env_type] ~= nil) and not use_nested
    local inline_env = use_inline and SMALL_ENV_INLINE[env_type] or (use_nested and nested_env) or nil
    local prepend_title = (use_inline or use_nested) and #content > 0
    
    if prepend_title then
        local first = content[1]
        local title_content = {}
        table.insert(title_content, pandoc.Emph({pandoc.Str(display_name)}))
        if title_inlines and #title_inlines > 0 then
            table.insert(title_content, pandoc.Str(" ("))
            for _, inline in ipairs(title_inlines) do
                table.insert(title_content, inline)
            end
            table.insert(title_content, pandoc.Str(")"))
        end
        table.insert(title_content, pandoc.Str("."))
        table.insert(title_content, pandoc.Space())
        if first.t == "Para" or first.t == "Plain" then
            for i = #title_content, 1, -1 do
                table.insert(first.content, 1, title_content[i])
            end
        else
            -- No Para/Plain to prepend to: insert new title paragraph
            table.insert(content, 1, pandoc.Para(title_content))
        end
    end
    
    -- Convert title inlines to LaTeX (for non-inline/non-nested envs)
    local title_str = ""
    if not prepend_title and title_inlines and #title_inlines > 0 then
        local doc = pandoc.Pandoc({pandoc.Para(title_inlines)})
        local latex = pandoc.write(doc, "latex")
        local body = latex:match("\\begin{document}%s*(.-)%s*\\end{document}")
        if body and body:match("%S") then
            title_str = body:gsub("^%s+", ""):gsub("%s+$", "")
        else
            title_str = latex:gsub("^%s+", ""):gsub("%s+$", "")
        end
    end
    
    -- Build begin command (use inline env when title is in content)
    local actual_env = inline_env or latex_env
    local begin_cmd
    if title_str ~= "" then
        -- Braces keep a "]" inside the title (e.g. "\\(F[x]\\)") from closing the optional argument early
        begin_cmd = string.format("\\begin{%s}[{%s}]", actual_env, title_str)
    else
        begin_cmd = string.format("\\begin{%s}", actual_env)
    end
    
    -- Add label if present
    if label_id and label_id ~= "" then
        begin_cmd = begin_cmd .. string.format("\\label{%s}", label_id)
    end
    
    local end_cmd = string.format("\\end{%s}", actual_env)
    
    -- Wrap content with begin/end
    local result = {}
    table.insert(result, pandoc.RawBlock("latex", begin_cmd))
    -- The optional marker: a quiet first line inside the box, set like the box's own
    -- furniture (latex/theorem-envs.sty), so it reads as part of the frame and not as a
    -- banner. After the \label, so a reference still points at the statement.
    if optional then
        table.insert(result, pandoc.RawBlock("latex", "\\bookoptionalnote"))
    end
    for _, block in ipairs(content) do
        table.insert(result, block)
    end
    table.insert(result, pandoc.RawBlock("latex", end_cmd))
    
    return result
end

-- =============================================================================
-- Label Scanning and Serialization
-- =============================================================================

-- Global registry loaded from metadata (for cross-chapter links)
local global_labels = {}

-- Load global labels. Read the JSON file directly: passing it through --metadata-file
-- would parse every string (including rendered HTML/LaTeX titles) as Markdown.
local function load_global_labels(meta)
    local path = meta["crossref-labels-file"]
    if not path then return end
    local f = io.open(pandoc.utils.stringify(path), "r")
    if not f then return end
    local data = pandoc.json.decode(f:read("*all"), false)
    f:close()
    for k, v in pairs(data.crossref_labels or {}) do
        global_labels[k] = v
    end
end

-- Other books' labels, cited as @prefix:label (config "external-books"; build/external.py
-- writes the file: per prefix the book's title, short name, url, formats, whether its
-- registry could be read, and the labels of it this book cites).
local external_books = {}

local function load_external_books(meta)
    local path = meta["external-books-file"]
    if not path then return end
    local f = io.open(pandoc.utils.stringify(path), "r")
    if not f then return end
    local data = pandoc.json.decode(f:read("*all"), false)
    f:close()
    external_books = type(data) == "table" and data or {}
end

local function html_escape(s)
    return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local LATEX_SPECIALS = { ["\\"] = "\\textbackslash{}", ["^"] = "\\textasciicircum{}",
                         ["~"] = "\\textasciitilde{}" }
local function latex_escape(s)
    return (s:gsub("[\\%%#&_{}%$%^~]", function(c) return LATEX_SPECIALS[c] or ("\\" .. c) end))
end

-- "{title}, {ref}" with the placeholders filled; unknown placeholders stay as written
local function fill(template, values)
    return (template:gsub("{(%w+)}", function(key) return values[key] end))
end

-- "Theorem 12.4", or "Example (Title)" for an unnumbered target: the same text a local
-- reference prints
local function external_ref_text(info, latex)
    local name = info.type_name or ""
    if info.number and info.number ~= "" then
        return name .. (latex and "~" or " ") .. info.number
    end
    local title = latex and info.title_latex or info.title_html
    if title and title ~= "" then return name .. " (" .. title .. ")" end
    return name
end

-- A reference into another book. Returns (inline, handled): handled is false when the id
-- is not @prefix:label for a configured prefix; inline is nil when the label is unknown
-- (the reference is then left as written, like an unresolved local one).
-- In-text @la:thm-x reads "Linear Algebra, Theorem 12.4" ("format"); bracketed
-- [@la:thm-x] reads "[LA, Theorem 12.4]" ("short-format").
local function external_reference(citation)
    local prefix, label = citation.id:match("^(%a[%w_]*):(.+)$")
    local ext = prefix and external_books[prefix]
    if not ext then return nil, false end
    local info = ext.labels and ext.labels[label]
    if ext.available and not info then
        io.stderr:write("Warning: unresolved reference @" .. citation.id .. " (no such label in "
                        .. tostring(ext.title) .. ")\n")
        return nil, true
    end
    local template = citation.mode == "NormalCitation" and ext["short-format"] or ext.format
    local url = ext.url or ""
    local absolute = url:match("^%a[%w+.-]*:") ~= nil or url:sub(1, 1) == "/"
    local target = url
    if info and info.file and info.file ~= "" then
        target = url .. info.file .. "#" .. label
    end
    if FORMAT:match("html") then
        local text = fill(template, { title = html_escape(ext.title or prefix),
            short = html_escape(ext.short or prefix),
            ref = info and external_ref_text(info, false) or html_escape(label) })
        if url == "" then return pandoc.RawInline("html", text), true end
        local prefix_path = ""
        if not absolute then
            prefix_path = doc_meta and doc_meta["asset-prefix"] and pandoc.utils.stringify(doc_meta["asset-prefix"]) or ""
        end
        local attrs = {}
        if info then
            -- main.js fetches the preview from <data-base>theorems/<shard>/<label>.json
            attrs = { {"data-ref", label}, {"data-shard", info.shard or ""},
                      {"data-base", prefix_path .. url}, {"data-book", ext.title or prefix} }
        end
        return pandoc.Link({pandoc.RawInline("html", text)}, prefix_path .. target, "",
                           pandoc.Attr("", {"xref", "xref-external"}, attrs)), true
    elseif FORMAT:match("latex") then
        local text = fill(template, { title = latex_escape(ext.title or prefix),
            short = latex_escape(ext.short or prefix),
            ref = info and external_ref_text(info, true) or latex_escape(label) })
        -- Only an absolute web address means anything in a PDF
        if url:match("^https?://") then
            local href = target:gsub("[#%%\\]", "\\%0")
            return pandoc.RawInline("latex", "\\href{" .. href .. "}{" .. text .. "}"), true
        end
        return pandoc.RawInline("latex", text), true
    end
    local plain = fill(template, { title = ext.title or prefix, short = ext.short or prefix,
        ref = info and external_ref_text(info, false) or label })
    return pandoc.Str(plain), true
end

-- Scan mode: collect labels and the references this file uses, print as JSON
local function scan_and_dump_labels(doc)
    local collected = {}
    local refs = {}
    -- Plain text for the search index, taken before the walk below edits the document
    -- (math kept as its TeX source; the plain writer would warn about every formula)
    local text_doc = doc:walk { Math = function(m) return pandoc.Str(m.text) end }
    local text = pandoc.write(text_doc, "plain", {wrap_text = "none"})
    -- Dependencies: the references made by each labeled result, counting its statement
    -- and the proofs, solutions and remarks that follow it (until the next result or
    -- heading). Collected before the walk below edits the document.
    local uses = {}
    local block_text = {}  -- label -> prose of its statement and proofs (for title mentions)
    do
        -- A proof (with its idea and claims) belongs to the last *result*, even when an
        -- example or exercise sits between the statement and the proof: crediting it to the
        -- example hid the fundamental theorem of algebra's citations from the dependency gate.
        -- Solutions, remarks, warnings and checks still belong to the block just before them.
        local RESULT_ENVS = { theorem = true, lemma = true, corollary = true, proposition = true, axiom = true }
        local PASS_OVER = { example = true, exercise = true }
        local PROOF_PARTS = { proof = true, proofofclaim = true, claim = true, idea = true }
        local current, current_kind, current_result = nil, nil, nil
        -- `kind` is the environment the citation was written in: the owning result's own
        -- type for its statement, or "proof", "idea", "remark", "solution" ... for a block
        -- that follows it. A consumer needs it to tell a proof's dependency (remove it and
        -- the theorem is unproved) from a remark's (remove it and a sentence is reworded).
        local function add_cites(block, owner, kind)
            if not owner then return end
            uses[owner] = uses[owner] or {}
            block:walk { Cite = function(cite)
                for _, citation in ipairs(cite.citations) do
                    if citation.id ~= owner then
                        local kinds = uses[owner][citation.id]
                        if not kinds then kinds = {}; uses[owner][citation.id] = kinds end
                        kinds[kind] = true
                    end
                end
            end }
            local without_math = block:walk { Math = function() return pandoc.Space() end }
            block_text[owner] = (block_text[owner] or "") .. " " .. pandoc.utils.stringify(without_math)
        end
        for _, block in ipairs(doc.blocks) do
            if block.t == "Header" then
                current, current_kind, current_result = nil, nil, nil
            elseif block.t == "Div" then
                local env_type = get_env_type(block)
                if env_type and ENV_STYLES[env_type] == "big" then
                    current = (block.identifier ~= "" and block.identifier) or nil
                    current_kind = env_type
                    if current then uses[current] = uses[current] or {} end
                    if RESULT_ENVS[env_type] then current_result = current end
                    add_cites(block, current, env_type)
                elseif env_type then
                    local owner = current
                    if PROOF_PARTS[env_type] and PASS_OVER[current_kind] and current_result then
                        owner = current_result
                    end
                    -- An explicit owner wins: `::: {.proof of="thm-x"}` for a proof set apart from
                    -- its statement (the theorem stated first, lemmas proved, the proof at the end)
                    local named = block.attributes and block.attributes["of"]
                    if named and named ~= "" then
                        owner = named
                        uses[owner] = uses[owner] or {}
                    end
                    add_cites(block, owner, env_type)
                end
            end
        end
    end
    -- Two views of the same data: `uses` stays the flat sorted list every consumer already
    -- reads, and `uses_kinds` adds, per cited label, the sorted environments that cited it.
    local uses_lists = {}
    local uses_kinds = {}
    for label, set in pairs(uses) do
        local list = {}
        local kinds_by_id = {}
        for id, kindset in pairs(set) do
            table.insert(list, id)
            local kinds = {}
            for kind in pairs(kindset) do table.insert(kinds, kind) end
            table.sort(kinds)
            kinds_by_id[id] = kinds
        end
        table.sort(list)
        uses_lists[label] = list
        uses_kinds[label] = kinds_by_id
    end

    -- Prose for the spell check: no mathematics, code or raw LaTeX
    local prose_doc = doc:walk {
        Math = function() return pandoc.Space() end,
        Code = function() return pandoc.Space() end,
        CodeBlock = function() return {} end,
        RawBlock = function() return {} end,
        RawInline = function() return pandoc.Space() end,
        Cite = function() return pandoc.Space() end,
    }
    local prose = pandoc.write(prose_doc, "plain", {wrap_text = "none"})
    -- Page description: leading top-level paragraphs without mathematics
    local description = {}
    for _, block in ipairs(doc.blocks) do
        if block.t == "Para" then
            local has_math = false
            block:walk { Math = function() has_math = true end }
            if has_math then
                if #description > 0 then break end
            else
                table.insert(description, pandoc.utils.stringify(block))
                if #table.concat(description, " ") > 160 then break end
            end
        elseif block.t ~= "Header" and #description > 0 then
            break
        end
    end
    
    -- Walk the document to find all theorem environments and equations
    doc:walk {
        Div = function(div)
            local env_type = get_env_type(div)
            if env_type then
                local label_id = get_label_id(div)
                local number = get_next_number(env_type)
                local title_inlines = extract_title(div) -- Destructive, but okay for scan
                
                if label_id and label_id ~= "" then
                    -- Render the content to HTML
                    local content_doc = pandoc.Pandoc(div.content)
                    
                    local status, html_content = pcall(pandoc.write, content_doc, 'html', {html_math_method = 'mathjax'})
                    if not status then
                         status, html_content = pcall(pandoc.write, content_doc, 'html')
                    end
                    if not status then
                        html_content = "Error rendering content: " .. tostring(html_content)
                    end
                    
                    local record = label_record(env_type, number, title_inlines)
                    record.html_content = html_content
                    record.id = label_id
                    -- Only optional results carry the field, so a consumer reading
                    -- crossref_labels.json can treat its absence as "required".
                    if is_optional(div) then record.optional = true end
                    collected[label_id] = record
                end
            end
        end,
        
        Para = function(para)
            local res = process_para_math(para, "scan")
            if res then
                local record = label_record(res.type, res.number, nil)
                record.html_content = res.html_content
                record.id = res.id
                collected[res.id] = record
            end
        end,
        
        Cite = function(cite)
            for _, citation in ipairs(cite.citations) do
                table.insert(refs, citation.id)
            end
        end
    }
    
    if doc.meta.scan_mode then
        local json_str = pandoc.json.encode({labels = collected, refs = refs, text = text,
            description = table.concat(description, " "), prose = prose, uses = uses_lists,
            uses_kinds = uses_kinds, block_text = block_text})
        print("SCAN_RESULT:" .. json_str)
        return pandoc.Pandoc({}, doc.meta)
    end
    
    return doc
end

-- =============================================================================
-- Main Filter Logic
-- =============================================================================

-- Recursively mark theorem divs nested inside another small env (avoids mdframed nesting in LaTeX)
local function mark_nested_blocks(blocks, inside_small_env)
    for _, block in ipairs(blocks) do
        if block.t == "Div" then
            local env_type = get_env_type(block)
            if env_type then
                local style = ENV_STYLES[env_type] or "big"
                local is_small = (style == "small")
                local key = get_div_key(block)
                if inside_small_env and is_small and SMALL_ENV_NESTED[env_type] then
                    nested_div_keys[key] = true
                end
                mark_nested_blocks(block.content, inside_small_env or is_small)
            else
                mark_nested_blocks(block.content, inside_small_env)
            end
        elseif block.t == "BlockQuote" and block.content then
            mark_nested_blocks(block.content, inside_small_env)
        elseif (block.t == "OrderedList" or block.t == "BulletList") and block.content then
            for _, item in ipairs(block.content) do
                mark_nested_blocks(item, inside_small_env)  -- item is list of blocks
            end
        end
    end
end

-- First pass: collect all labels and process environments
local function collect_labels(div)
    -- Book mode: file-boundary markers; inject \setcounter or \part for structure
    local attrs = div.attr and div.attr.attributes or {}
    if attrs["data-chapter"] or attrs["data-section"] then
        local new_c = attrs["data-chapter"] and (tonumber(pandoc.utils.stringify(attrs["data-chapter"])) or 0) or current_file_chapter
        local new_s = attrs["data-section"] and (tonumber(pandoc.utils.stringify(attrs["data-section"])) or 0) or current_file_section
        local is_preface = attrs["data-preface"] and pandoc.utils.stringify(attrs["data-preface"]) == "true"
        local chap_title = attrs["data-chapter-title"] and pandoc.utils.stringify(attrs["data-chapter-title"]) or ""
        current_file_chapter = new_c
        current_file_section = new_s
        current_file_is_preface = is_preface
        counters.chapter = new_c
        counters.section = new_s
        if FORMAT:match("latex") and is_book_mode() then
            -- Each file's H1 is a LaTeX \chapter, numbered part.chapter (e.g. 1.6). Set the
            -- counter explicitly so it matches the web numbering from the file position,
            -- instead of counting chapter index pages as chapters.
            local tex = ""
            if is_preface then
                last_book_part = -1
                tex = "\\prefacebanner{Preface}\\setcounter{part}{-1}"
            elseif last_book_part ~= new_c then
                last_book_part = new_c
                local part_title = attrs["data-part-title"] and pandoc.utils.stringify(attrs["data-part-title"]) or ""
                if part_title ~= "" then
                    tex = tex .. "\\bookpartdivider{" .. part_title .. "}"
                end
                -- \part increments the counter; set it so the part number is the chapter number
                tex = string.format("\\setcounter{part}{%d}", new_c - 1)
                if new_c == 0 then
                    tex = tex .. "\\part{" .. ((chap_title ~= "") and chap_title or "Chapter 0") .. "}"
                elseif chap_title ~= "" then
                    tex = tex .. "\\part{Chapter " .. new_c .. ": " .. chap_title .. "}"
                else
                    tex = tex .. "\\part{Chapter " .. new_c .. "}"
                end
            end
            tex = tex .. string.format("\\setcounter{chapter}{%d}\\setcounter{section}{0}", math.max(new_s - 1, 0))
            return {pandoc.RawBlock("latex", tex)}
        end
        return {}  -- Remove marker from output
    end
    local env_type = get_env_type(div)
    if not env_type then return nil end
    
    local label_id = get_label_id(div)
    local title_inlines = extract_title(div)
    local number = get_next_number(env_type)
    
    local key = get_div_key(div)
    processed_envs[key] = {
        number = number,
        title_inlines = title_inlines,
        is_nested = nested_div_keys[key] or false,
    }
    
    if label_id and label_id ~= "" then
        labels[label_id] = label_record(env_type, number, title_inlines)
    end
    
    return div
end

-- Second pass: render environments and resolve cross-refs
local function render_environment(div)
    local env_type = get_env_type(div)
    if not env_type then return nil end
    
    local label_id = get_label_id(div)
    local key = get_div_key(div)
    local processed = processed_envs[key]
    
    local number = processed and processed.number or nil
    local title_inlines = processed and processed.title_inlines or nil
    
    local is_nested = processed and processed.is_nested or false
    local optional = is_optional(div)
    if FORMAT:match("html") then
        return render_env_html(env_type, number, title_inlines, label_id, div.content, optional)
    elseif FORMAT:match("latex") then
        return render_env_latex(env_type, number, title_inlines, label_id, div.content,
                                is_nested, optional)
    else
        return nil  -- Keep original for other formats
    end
end

-- Cross-Reference Resolution
-- Numbered targets read "Theorem 1.2.3"; unnumbered ones (examples) read "Example (Title)".
-- HTML and LaTeX produce the same text.
local function process_citations(cite)
    local refs = {}
    for _, citation in ipairs(cite.citations) do
        local id = citation.id
        local label_info = labels[id] or global_labels[id]
        local external, is_external = nil, false
        if not label_info then external, is_external = external_reference(citation) end

        if is_external then
            if not external then return nil end
            table.insert(refs, external)
        elseif label_info then
            local numbered = label_info.number and label_info.number ~= ""
            local name = label_info.type_name
            
            if FORMAT:match("html") then
                local text = name
                if numbered then
                    text = name .. " " .. label_info.number
                elseif label_info.title_html and label_info.title_html ~= "" then
                    text = name .. " (" .. label_info.title_html .. ")"
                end
                -- Same-document labels have no file; others are relative to the site root
                local target_url = "#" .. id
                if label_info.file and label_info.file ~= "" then
                   local prefix = doc_meta and doc_meta["asset-prefix"] and pandoc.utils.stringify(doc_meta["asset-prefix"]) or ""
                   target_url = prefix .. label_info.file .. "#" .. id
                end
                table.insert(refs, pandoc.Link(
                    {pandoc.RawInline("html", text)},
                    target_url,
                    "",
                    pandoc.Attr("", {"xref"}, {{"data-ref", id}, {"data-shard", label_info.shard or page_shard()}})
                ))
            elseif FORMAT:match("latex") then
                -- A label defined in another section's file cannot be \\ref'd from this
                -- section's PDF; print its number instead (the book PDF has all labels)
                local in_document = labels[id] ~= nil or is_book_mode()
                local text
                if numbered and in_document then
                    text = string.format("%s~\\ref*{%s}", name, id)
                elseif numbered then
                    text = name .. "~" .. label_info.number
                elseif label_info.title_latex and label_info.title_latex ~= "" then
                    text = name .. " (" .. label_info.title_latex .. ")"
                else
                    text = name
                end
                if in_document then
                    table.insert(refs, pandoc.RawInline("latex", string.format("\\hyperref[%s]{%s}", id, text)))
                else
                    table.insert(refs, pandoc.RawInline("latex", text))
                end
            else
                table.insert(refs, pandoc.Str(numbered and (name .. " " .. label_info.number) or name))
            end
        else
            -- Leave the text alone: @name may be a real citation or an email-like string
            if id:match("^%a+%-") then
                io.stderr:write("Warning: unresolved reference @" .. id .. "\n")
            elseif id:match("^%a[%w_]*:%a+%-") then
                io.stderr:write("Warning: unresolved reference @" .. id
                                .. " (no such book prefix in the config's external-books)\n")
            end
            return nil
        end
    end
    
    if #refs == 1 then
        return refs[1]
    else
        local result = {}
        for i, ref in ipairs(refs) do
            if i > 1 then
                table.insert(result, pandoc.Str(", "))
            end
            table.insert(result, ref)
        end
        return pandoc.Span(result)
    end
end

-- In LaTeX, chapter index pages (section 0) have unnumbered titles, matching the web,
-- so they don't take a chapter number from the sections that follow.
local function unnumber_index_titles(doc)
    if not FORMAT:match("latex") then return end
    local function mark(header)
        if header.level == 1 and not header.classes:includes("unnumbered") then
            header.classes:insert("unnumbered")
        end
    end
    if is_book_mode() then
        local in_index = false
        for _, block in ipairs(doc.blocks) do
            if block.t == "Div" and block.attributes["data-section"] then
                in_index = block.attributes["data-section"] == "0" and not block.attributes["data-preface"]
            elseif block.t == "Header" and in_index then
                mark(block)
            end
        end
    elseif counters.section == 0 and pandoc.utils.stringify(doc.meta["is-preface"] or "") ~= "true" then
        for _, block in ipairs(doc.blocks) do
            if block.t == "Header" then mark(block) end
        end
    end
end

return {
    -- First pass: initialize and scanning
    {
        Pandoc = function(doc)
            doc_meta = doc.meta
            init_counters(doc.meta)
            load_global_labels(doc.meta)
            load_external_books(doc.meta)
            nested_div_keys = {}
            current_file_chapter = 0
            current_file_section = 0
            current_file_is_preface = false
            last_book_part = -2
            mark_nested_blocks(doc.blocks, false)
            unnumber_index_titles(doc)
            
            if doc.meta.scan_mode then
                return scan_and_dump_labels(doc)
            end
            
            return doc
        end
    },
    {
        Div = collect_labels,
        Para = function(p) return process_para_math(p, "collect") end
    },
    -- Second pass: render and resolve
    {
        Div = render_environment,
        Para = function(p) return process_para_math(p, "render") end,
        Cite = process_citations,
    }
}
