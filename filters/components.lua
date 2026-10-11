--[[
Interactive Components Filter
=============================
Three components, each with a web form and a print form:

Runnable code cell
    ```{.python .run #cell-id packages="numpy,sympy"}
    ...
    ```
    HTML: editable cell run in the browser with Pyodide.
    LaTeX: a code listing, plus a link to the online version when deploy-domain is set.

Function plot
    ::: {.plot fn="sin(a*x); cos(x)" x="-6.28,6.28" y="-2,2" params="a=1:0..3"}
    Optional caption.
    :::
    HTML: JSXGraph plot with a slider per parameter.
    LaTeX: pgfplots, with parameters at their default values.
    Expressions: numbers, x, parameters, pi, e, + - * / ^, parentheses and
    sin cos tan asin acos atan sinh cosh tanh exp log sqrt abs (log is natural).

Widget (custom JavaScript)
    ::: {.widget src="widgets/linear-map.js" matrix="1,1,0,1"}
    ::: {.print}
    Content for the PDF and for readers without JavaScript.
    :::
    :::
    HTML: the module's default export is called with a mount element; the print
    content is shown until it mounts. LaTeX: only the print content.

Second-reading fold (not interactive, but it has a web form and a print form too)
    ::: {.second-reading title="Why the order is loss-free"}
    Material a first reading may skip: a meta-proof, edge cases, a long justification.
    :::
    HTML: a <details> closed by default, whose <summary> shows a marker and the title
    ("Second reading" without one). LaTeX: the content inline, between light rules, under
    a head with the same marker and the title. The fold is display only: its content is
    turned into blocks of the enclosing list *before* theorems.lua runs, so environments
    inside it are numbered, labelled, cited and previewed exactly as outside it, and the
    label scan (search text, dependencies) sees them as main-line blocks. A fold inside a
    fold, and a heading inside a fold, are reported as errors.

Problems (bad expressions, missing print content, unknown widget file) are written to
stderr; in scan mode they are printed as COMPONENT_ERROR lines for ./build.py check.
]]

local is_html = FORMAT:match("html") ~= nil
local is_latex = FORMAT:match("latex") ~= nil

local settings = {
    scan_mode = false,
    asset_prefix = "./",
    book_root = nil,
    page_url = nil,
    source = "",
}
local has_components = false
local cell_count = 0

local function report(message)
    if settings.scan_mode then
        print("COMPONENT_ERROR:" .. pandoc.json.encode({message = message}))
    else
        io.stderr:write("Warning: " .. message .. "\n")
    end
end


-- =============================================================================
-- Expressions (same grammar as templates/html/components/expression.js)
-- =============================================================================

local FUNCTIONS = {
    sin = "sin", cos = "cos", tan = "tan", asin = "asin", acos = "acos", atan = "atan",
    sinh = "sinh", cosh = "cosh", tanh = "tanh", exp = "exp", log = "ln", sqrt = "sqrt", abs = "abs",
}
local CONSTANTS = { pi = "pi", e = "e" }

local function tokenize(text)
    local tokens = {}
    local i = 1
    while i <= #text do
        local c = text:sub(i, i)
        if c:match("%s") then
            i = i + 1
        else
            local number = text:match("^%d+%.?%d*[eE][%+%-]?%d+", i) or text:match("^%d+%.?%d*", i)
                or text:match("^%.%d+", i)
            local name = text:match("^[%a_][%w_]*", i)
            if number then
                table.insert(tokens, {kind = "num", value = number})
                i = i + #number
            elseif name then
                table.insert(tokens, {kind = "name", value = name})
                i = i + #name
            elseif c:match("[%+%-%*/%^%(%)]") then
                table.insert(tokens, {kind = c})
                i = i + 1
            else
                error("unexpected character '" .. c .. "'", 0)
            end
        end
    end
    return tokens
end

-- Parse into nested tables: {num=}, {var=}, {call=, arg=}, {neg=}, {op=, a=, b=}
local function parse_expression(text, variables)
    local tokens = tokenize(text)
    local pos = 1
    local function peek() return tokens[pos] and tokens[pos].kind end
    -- An operand directly after another (2x, x(x+1)) is a missing multiplication sign
    local function missing_operator()
        local token = tokens[pos]
        if token and (token.kind == "num" or token.kind == "name" or token.kind == "(") then
            error("missing '*' before '" .. (token.value or token.kind) .. "'", 0)
        end
    end
    local function take(kind)
        if peek() ~= kind then
            missing_operator()
            error("expected '" .. kind .. "'" .. (tokens[pos] and "" or " at end"), 0)
        end
        pos = pos + 1
        return tokens[pos - 1]
    end

    local expr, unary
    local function primary()
        local token = tokens[pos]
        if not token then error("unexpected end of expression", 0) end
        if token.kind == "num" then
            pos = pos + 1
            return {num = token.value}
        elseif token.kind == "(" then
            pos = pos + 1
            local inner = expr()
            take(")")
            return inner
        elseif token.kind == "name" then
            pos = pos + 1
            if peek() == "(" then
                if not FUNCTIONS[token.value] then error("unknown function '" .. token.value .. "'", 0) end
                take("(")
                local arg = expr()
                take(")")
                return {call = token.value, arg = arg}
            end
            if token.value == "x" or variables[token.value] or CONSTANTS[token.value] then
                return {var = token.value}
            end
            error("unknown name '" .. token.value .. "'", 0)
        end
        error("unexpected '" .. token.kind .. "'", 0)
    end
    local function power()
        local base = primary()
        if peek() == "^" then
            pos = pos + 1
            return {op = "^", a = base, b = unary()}
        end
        return base
    end
    unary = function()
        if peek() == "-" then
            pos = pos + 1
            return {neg = unary()}
        end
        return power()
    end
    local function term()
        local left = unary()
        while peek() == "*" or peek() == "/" do
            local op = take(peek()).kind
            left = {op = op, a = left, b = unary()}
        end
        return left
    end
    expr = function()
        local left = term()
        while peek() == "+" or peek() == "-" do
            local op = take(peek()).kind
            left = {op = op, a = left, b = term()}
        end
        return left
    end

    local tree = expr()
    if pos <= #tokens then
        missing_operator()
        error("unexpected '" .. (tokens[pos].value or tokens[pos].kind) .. "'", 0)
    end
    return tree
end

-- pgfplots expression, fully parenthesized; parameters replaced by their values
local function to_pgf(node, values)
    if node.num then return node.num end
    if node.var then
        if node.var == "x" then return "x" end
        if CONSTANTS[node.var] then return CONSTANTS[node.var] end
        return "(" .. values[node.var] .. ")"
    end
    if node.call then return FUNCTIONS[node.call] .. "(" .. to_pgf(node.arg, values) .. ")" end
    if node.neg then return "(-" .. to_pgf(node.neg, values) .. ")" end
    return "(" .. to_pgf(node.a, values) .. node.op .. to_pgf(node.b, values) .. ")"
end

-- "a=1:0..3, b=0.5:-1..1" -> list of {name, default, min, max}
local function parse_params(text)
    local params = {}
    for item in (text or ""):gmatch("[^,]+") do
        local name, default, low, high = item:match("^%s*([%a_][%w_]*)%s*=%s*([%-%d%.eE]+)%s*:%s*([%-%d%.eE]+)%s*%.%.%s*([%-%d%.eE]+)%s*$")
        if not name or not tonumber(default) or not tonumber(low) or not tonumber(high) then
            error("bad parameter '" .. item .. "' (expected name=default:min..max)", 0)
        end
        table.insert(params, {name = name, default = default, min = low, max = high})
    end
    return params
end

local function parse_range(text, name)
    local low, high = (text or ""):match("^%s*([%-%d%.eE]+)%s*,%s*([%-%d%.eE]+)%s*$")
    if not low or not tonumber(low) or not tonumber(high) or tonumber(low) >= tonumber(high) then
        error(name .. " must be 'min,max' with min < max", 0)
    end
    return low, high
end

-- =============================================================================
-- Code Cells
-- =============================================================================

local function code_cell(block)
    local lang = nil
    for _, class in ipairs(block.classes) do
        if class ~= "run" then lang = class break end
    end
    if lang ~= "python" then
        report("runnable cells support python only (got " .. tostring(lang) .. ") in " .. settings.source)
        return nil
    end
    cell_count = cell_count + 1
    local id = block.identifier ~= "" and block.identifier or ("cell-" .. cell_count)
    local packages = block.attributes["packages"] or ""

    if is_latex then
        local blocks = {pandoc.RawBlock("latex", "\\begin{lstlisting}[language=Python]\n" .. block.text .. "\n\\end{lstlisting}")}
        if settings.page_url then
            -- Link text rather than the URL itself, which would run past the margin
            table.insert(blocks, pandoc.Para({
                pandoc.Emph({pandoc.Link({pandoc.Str("Run"), pandoc.Space(), pandoc.Str("this"), pandoc.Space(),
                    pandoc.Str("code"), pandoc.Space(), pandoc.Str("online")}, settings.page_url .. "#" .. id)}),
            }))
        end
        return blocks
    end

    if is_html then
        has_components = true
        local listing = pandoc.CodeBlock(block.text, pandoc.Attr("", {lang}))
        local controls = pandoc.RawBlock("html", [[
<div class="code-cell-toolbar">
<button type="button" class="code-cell-run" title="Run (Shift+Enter)">Run</button>
<button type="button" class="code-cell-reset" hidden>Reset</button>
<span class="code-cell-status" aria-live="polite"></span>
</div>
<div class="code-cell-output" hidden></div>]])
        return pandoc.Div({listing, controls},
            pandoc.Attr(id, {"code-cell"}, {{"data-lang", lang}, {"data-packages", packages}}))
    end
    return nil
end

-- =============================================================================
-- Plots
-- =============================================================================

local PGF_COLORS = {"blue", "red!80!black", "green!50!black", "orange"}

local function plot(div)
    local fn = div.attributes["fn"]
    local ok, result = pcall(function()
        if not fn or fn == "" then error("missing fn attribute", 0) end
        local params = parse_params(div.attributes["params"])
        local variables, values = {}, {}
        for _, p in ipairs(params) do
            variables[p.name] = true
            values[p.name] = p.default
        end
        local xmin, xmax = parse_range(div.attributes["x"] or "-5,5", "x")
        local ymin, ymax
        if div.attributes["y"] then ymin, ymax = parse_range(div.attributes["y"], "y") end
        local functions = {}
        for part in fn:gmatch("[^;]+") do
            local tree = parse_expression(part, variables)
            table.insert(functions, to_pgf(tree, values))
        end
        return {functions = functions, xmin = xmin, xmax = xmax, ymin = ymin, ymax = ymax}
    end)
    if not ok then
        report("plot fn=\"" .. tostring(fn) .. "\" in " .. settings.source .. ": " .. tostring(result))
        return nil
    end

    if is_latex then
        local axis = {
            "axis lines=middle", "width=0.75\\linewidth", "height=0.45\\linewidth",
            "xmin=" .. result.xmin, "xmax=" .. result.xmax, "domain=" .. result.xmin .. ":" .. result.xmax,
            "samples=200", "trig format plots=rad", "unbounded coords=jump",
            "xlabel={$x$}", "ylabel={$y$}",
        }
        if result.ymin then
            local span = tonumber(result.ymax) - tonumber(result.ymin)
            table.insert(axis, "ymin=" .. result.ymin)
            table.insert(axis, "ymax=" .. result.ymax)
            table.insert(axis, string.format("restrict y to domain=%g:%g", tonumber(result.ymin) - span, tonumber(result.ymax) + span))
        end
        local lines = {"\\begin{center}", "\\begin{tikzpicture}", "\\begin{axis}[" .. table.concat(axis, ", ") .. "]"}
        for i, expression in ipairs(result.functions) do
            table.insert(lines, string.format("\\addplot[thick, %s] {%s};", PGF_COLORS[(i - 1) % #PGF_COLORS + 1], expression))
        end
        table.insert(lines, "\\end{axis}")
        table.insert(lines, "\\end{tikzpicture}")
        table.insert(lines, "\\end{center}")
        local blocks = {pandoc.RawBlock("latex", table.concat(lines, "\n"))}
        for _, block in ipairs(div.content) do table.insert(blocks, block) end
        return blocks
    end

    if is_html then
        has_components = true
        local content = {pandoc.RawBlock("html", '<div class="plot-board"></div><div class="plot-controls"></div>')}
        if #div.content > 0 then
            table.insert(content, pandoc.Div(div.content, pandoc.Attr("", {"plot-caption"})))
        end
        div.content = content
        return div
    end
    return nil
end

-- =============================================================================
-- Widgets
-- =============================================================================

local function widget(div)
    local src = div.attributes["src"]
    local print_blocks = nil
    local others = {}
    for _, block in ipairs(div.content) do
        if block.t == "Div" and block.classes:includes("print") then
            print_blocks = block.content
        else
            table.insert(others, block)
        end
    end

    if not src or src == "" then
        report("widget without src in " .. settings.source)
    elseif settings.book_root then
        local path = settings.book_root .. "/" .. src
        local engine_path = settings.engine_root and (settings.engine_root .. "/" .. src)
        local f = io.open(path, "r") or (engine_path and io.open(engine_path, "r"))
        if f then f:close() else report("widget file not found: " .. src .. " (in " .. settings.source .. ")") end
    end
    if not print_blocks then
        report("widget " .. tostring(src) .. " in " .. settings.source .. " has no ::: {.print} content for the PDF")
        print_blocks = {}
    end

    if is_latex then
        return print_blocks
    end
    if is_html then
        has_components = true
        div.attributes["src"] = nil
        div.attributes["data-src"] = settings.asset_prefix .. (src or "")
        local content = {pandoc.RawBlock("html", '<div class="widget-mount"></div>')}
        table.insert(content, pandoc.Div(print_blocks, pandoc.Attr("", {"widget-fallback"})))
        for _, block in ipairs(others) do table.insert(content, block) end
        div.content = content
        return div
    end
    return nil
end

-- =============================================================================
-- Second-reading folds
-- =============================================================================

local SECOND_READING = "Second reading"
-- The marker each format's opening block carries, so a fold found inside another can be told
local FOLD_OPEN_HTML = '<details class="second-reading"'
local FOLD_OPEN_LATEX = "\\begin{booksecondreading}"
local FOLD_MARK_SCAN = "<!-- second-reading -->"

local function title_inlines(text)
    if not text or not text:match("%S") then return nil end
    local doc = pandoc.read(text, "markdown+tex_math_single_backslash")
    local first = doc.blocks[1]
    if first and (first.t == "Para" or first.t == "Plain") then return first.content end
    return {pandoc.Str(text)}
end

local function is_fold_marker(block)
    return block.t == "RawBlock" and (block.text:find(FOLD_OPEN_HTML, 1, true)
        or block.text:find(FOLD_OPEN_LATEX, 1, true) or block.text:find(FOLD_MARK_SCAN, 1, true)
        or block.text == "</div></details>" or block.text == "\\end{booksecondreading}"
        or block.text == "<!-- /second-reading -->")
end

local function second_reading(div)
    local title = title_inlines(div.attributes["title"])
    local nested, heading = false, false
    div.content:walk {
        RawBlock = function(block) if is_fold_marker(block) then nested = true end end,
        Header = function() heading = true end,
    }
    local where = settings.source
    if nested then
        report("second-reading fold inside another second-reading fold in " .. where
            .. " (folds do not nest: close the first before opening the next)")
        -- Keep the text, drop the inner fold's frame
        div.content = div.content:walk { RawBlock = function(block)
            if is_fold_marker(block) then return {} end
        end, Plain = function(plain)
            if plain.content[1] and plain.content[1].t == "RawInline"
                and plain.content[1].text:find("<summary", 1, true) then return {} end
        end }
    end
    if heading then
        report("heading inside a second-reading fold in " .. where
            .. " (a fold sits inside a section; use a bold lead-in instead)")
    end

    local blocks = {}
    if is_html then
        local head = {pandoc.RawInline("html",
            '<summary><span class="second-reading-marker" aria-hidden="true">\u{21BA}</span>')}
        if title then
            table.insert(head, pandoc.RawInline("html",
                '<span class="second-reading-kicker">' .. SECOND_READING .. '</span><span class="second-reading-title">'))
            for _, inline in ipairs(title) do table.insert(head, inline) end
        else
            table.insert(head, pandoc.RawInline("html", '<span class="second-reading-title">' .. SECOND_READING))
        end
        table.insert(head, pandoc.RawInline("html", '</span></summary>'))
        table.insert(blocks, pandoc.RawBlock("html", FOLD_OPEN_HTML .. ">"))
        table.insert(blocks, pandoc.Plain(head))
        table.insert(blocks, pandoc.RawBlock("html", '<div class="second-reading-body">'))
        for _, block in ipairs(div.content) do table.insert(blocks, block) end
        table.insert(blocks, pandoc.RawBlock("html", "</div></details>"))
        return blocks
    end
    if is_latex then
        local head = SECOND_READING
        if title then
            local latex = pandoc.write(pandoc.Pandoc({pandoc.Plain(title)}), "latex")
            head = latex:gsub("^%s+", ""):gsub("%s+$", "")
        end
        -- Braces: a title may contain "]" or ","
        table.insert(blocks, pandoc.RawBlock("latex",
            FOLD_OPEN_LATEX .. "{" .. (title and "1" or "0") .. "}{" .. head .. "}"))
        for _, block in ipairs(div.content) do table.insert(blocks, block) end
        table.insert(blocks, pandoc.RawBlock("latex", "\\end{booksecondreading}"))
        return blocks
    end
    -- Any other format (the label scan writes JSON): the content as main-line blocks, between
    -- comments that every text the scan takes (search, prose, dependencies) ignores
    table.insert(blocks, pandoc.RawBlock("html", FOLD_MARK_SCAN))
    for _, block in ipairs(div.content) do table.insert(blocks, block) end
    table.insert(blocks, pandoc.RawBlock("html", "<!-- /second-reading -->"))
    return blocks
end

-- =============================================================================
-- Filter
-- =============================================================================

local function Meta(meta)
    local function get(key)
        return meta[key] and pandoc.utils.stringify(meta[key]) or nil
    end
    settings.scan_mode = get("scan_mode") == "true"
    settings.asset_prefix = get("asset-prefix") or "./"
    settings.book_root = get("book-root")
    settings.engine_root = get("engine-root")
    settings.page_url = get("page-url")
    settings.source = get("source-path") or "page"
end

local function Div(div)
    if div.classes:includes("plot") then return plot(div) end
    if div.classes:includes("widget") then return widget(div) end
    if div.classes:includes("second-reading") then return second_reading(div) end
    return nil
end

local function CodeBlock(block)
    if block.classes:includes("run") then return code_cell(block) end
    return nil
end

local function Pandoc(doc)
    if has_components and is_html then
        doc.meta["has-components"] = true
    end
    return doc
end

return {
    { Meta = Meta },
    { Div = Div, CodeBlock = CodeBlock },
    { Pandoc = Pandoc },
}
