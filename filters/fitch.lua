--[[
Fitch Filter
============
HTML output only. A raw LaTeX block holding Fitch-style derivations (the `nd` environment
of fitch.sty, as a book's latex/fitch-book.sty sets it up) becomes HTML: a grid of rows,
each a line number, the formula with its scope bars, and the justification. Formulas,
flag names and rule names are left as \( ... \) for MathJax, so they are set in the page's
math font, with the book's macros, and follow the theme (dark mode included).

Runs before filters/tikz.lua and only when the metadata says so ("fitch-html", set by
build/pandoc.py from the config key of that name; on by default when the book ships
fitch-book.sty). A block it cannot read is left alone, so tikz.lua compiles it to an
SVG as before, and a warning names the page and the reason. The LaTeX/PDF output never
sees this filter.

The layout follows fitch.sty: one vertical bar for the whole derivation (outerline), one
more per open box (\open ... \close), indented by a fixed step; a bar starts a little
below the top of its box's first row, so two sibling boxes (\close \open) stay apart;
the last of consecutive assumptions (\hypo) is underlined from its bar to just past the
formula; a flag (\open[x_0], \hypo{i}[x_0]{...}, \guard{x_0}) is printed in the indent
just left of its box's bar, on the box's first row. Line numbers follow fitch.sty's
counter (\have[base][offset] ...), \begin{nd}[schema] prints each line's own label, and
line references print the cited line's number ("3-5" as 3–5).

The rule macros (\ai, \ie, \raa, ...) are read from the book's fitch-book.sty
(`\def\ai{\by{$\wedge$I}}`); fitch.sty's own set is the fallback. A rule name is set
with the book's \rulename macro when its macros define one, else \mathrm.
]]

if not FORMAT:match("html") then
    return {}
end

local enabled = false
local rule_macro = "\\mathrm"
local source_path = "?"
local RULES = {   -- fitch.sty's default \ndrules, replaced by the book's sty when it has any
    ii = "$\\Rightarrow$I", ie = "$\\Rightarrow$E", Ai = "$\\forall$I", Ae = "$\\forall$E",
    Ei = "$\\exists$I", Ee = "$\\exists$E", ai = "$\\wedge$I", ae = "$\\wedge$E",
    oi = "$\\vee$I", oe = "$\\vee$E", ni = "$\\neg$I", ne = "$\\neg$E", be = "$\\bot$E",
    nne = "$\\neg\\neg$E", r = "R",
}

-- =============================================================================
-- Reading TeX
-- =============================================================================

local function skip_space(s, i)
    local _, e = s:find("^%s*", i)
    return e + 1
end

-- A balanced {...} group at or after i: (content, index after it) or (nil, i)
local function read_group(s, i)
    local j = skip_space(s, i)
    if s:sub(j, j) ~= "{" then return nil, i end
    local depth, k = 0, j
    while k <= #s do
        local c = s:sub(k, k)
        if c == "\\" then
            k = k + 1
        elseif c == "{" then
            depth = depth + 1
        elseif c == "}" then
            depth = depth - 1
            if depth == 0 then return s:sub(j + 1, k - 1), k + 1 end
        end
        k = k + 1
    end
    error("unbalanced braces", 0)
end

-- An optional [...] argument at or after i: (content, index after it) or (nil, i)
local function read_opt(s, i)
    local j = skip_space(s, i)
    if s:sub(j, j) ~= "[" then return nil, i end
    local depth, k = 0, j + 1
    while k <= #s do
        local c = s:sub(k, k)
        if c == "\\" then
            k = k + 1
        elseif c == "{" then
            depth = depth + 1
        elseif c == "}" then
            depth = depth - 1
        elseif c == "]" and depth == 0 then
            return s:sub(j + 1, k - 1), k + 1
        end
        k = k + 1
    end
    error("unbalanced [ in an optional argument", 0)
end

-- Drop TeX comments (% to the end of the line, not \%); markers such as
-- "% expect-invalid" and "% schema" are comments and go with them.
local function strip_comments(text)
    local out = {}
    for line in (text .. "\n"):gmatch("(.-)\n") do
        local k, cut = 1, nil
        while k <= #line do
            local c = line:sub(k, k)
            if c == "\\" then
                k = k + 1
            elseif c == "%" then
                cut = k
                break
            end
            k = k + 1
        end
        table.insert(out, cut and line:sub(1, cut - 1) or line)
    end
    return table.concat(out, "\n")
end

local function trim(s)
    return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- =============================================================================
-- HTML pieces
-- =============================================================================

local function escape(s)
    return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local function math(tex)
    tex = trim(tex)
    if tex == "" then return "" end
    return "\\(" .. escape(tex) .. "\\)"
end

-- A base that prints nothing, such as the \  of \have[\ ][0]
local function blank(tex)
    return (tex:gsub("\\[ ,;:!]", ""):gsub("~", ""):gsub("%s", "")) == ""
end

-- A printed line number (math in fitch.sty): digits as text, anything else as math
local function number_html(display)
    if blank(display) then return "" end
    local d = trim(display)
    if d:match("^[%d+-]+$") then return escape(d) end
    return math(d)
end

-- Text-mode TeX of a \by justification: $...$ becomes math, a few text commands are
-- read, anything else is an error (the block then falls back to the SVG).
local function text_html(tex)
    local parts, i = {}, 1
    while i <= #tex do
        local s = tex:find("$", i, true)
        while s and s > 1 and tex:sub(s - 1, s - 1) == "\\" do s = tex:find("$", s + 1, true) end
        local text = tex:sub(i, (s or #tex + 1) - 1)
        text = text:gsub("\\[ ]", " "):gsub("\\,", "\u{2009}"):gsub("~", "\u{00A0}")
                   :gsub("%-%-%-", "\u{2014}"):gsub("%-%-", "\u{2013}"):gsub("\\%$", "$")
                   :gsub("\\([&%%#_])", "%1"):gsub("[{}]", "")
        local command = text:match("\\%a+")
        if command then error("unsupported command " .. command .. " in a justification", 0) end
        table.insert(parts, escape(text))
        if not s then break end
        local e = tex:find("$", s + 1, true)
        if not e then error("unbalanced $ in a justification", 0) end
        table.insert(parts, math(tex:sub(s + 1, e - 1)))
        i = e + 1
    end
    return table.concat(parts)
end

-- A rule name such as "$\wedge$I" set as \rulename{{\wedge}I}
local function rule_html(text)
    if text:find("%s") then return text_html(text) end
    return math(rule_macro .. "{" .. text:gsub("%$(.-)%$", "{%1}") .. "}")
end

-- fitch.sty's \ndref: "1,3" -> "1, 3", "3-5" -> "3–5"; each label prints its line's number
local SEPARATORS = { ["-"] = "\u{2013}", [","] = ", ", [";"] = "; ", ["."] = ". ", ["("] = "(", [")"] = ")" }

local function refs_html(refs, numbers)
    local out, label = {}, ""
    local function flush()
        local l = trim(label)
        if l ~= "" then
            local shown = numbers[l]
            -- fitch.sty keeps a label's number for the rest of the document, so a label this
            -- derivation lacks is an earlier one's on the page: in practice the label itself
            table.insert(out, number_html(shown or l))
        end
        label = ""
    end
    for c in refs:gmatch(".") do
        if SEPARATORS[c] then
            flush()
            table.insert(out, SEPARATORS[c])
        else
            label = label .. c
        end
    end
    flush()
    return table.concat(out)
end

-- =============================================================================
-- One derivation
-- =============================================================================

local LINE_COMMANDS = { hypo = true, have = true, open = true, close = true, guard = true }

local function parse_nd(body, options)
    local schema = false
    local outerline = true
    for item in (options or ""):gmatch("[^,]+") do
        local key, value = item:match("^%s*([%w-]+)%s*=?%s*(.-)%s*$")
        if key == "schema" then schema = value ~= "false" end
        if key == "outerline" then outerline = value ~= "false" end
    end

    local rows, stack, numbers = {}, {}, {}
    local outer = { fresh = true }
    local pending = nil          -- the last row, while a following \hypo may still un-underline it
    local base, ctr = "", 1
    local pos = 1
    while true do
        pos = skip_space(body, pos)
        if pos > #body then break end
        local name = body:match("^\\(%a+)", pos)
        if not name or not LINE_COMMANDS[name] then
            error("unexpected `" .. body:sub(pos, pos + 15):gsub("%s+", " ") .. "`", 0)
        end
        pos = pos + #name + 1
        if name == "open" then
            local guard
            guard, pos = read_opt(body, pos)
            table.insert(stack, { fresh = true, guard = (guard and trim(guard) ~= "") and guard or nil })
            pending = nil
        elseif name == "close" then
            if #stack == 0 then error("\\close without \\open", 0) end
            table.remove(stack)
            pending = nil
        elseif name == "guard" then
            local n, guard
            n, pos = read_opt(body, pos)
            guard, pos = read_group(body, pos)
            local depth = tonumber(n and trim(n) ~= "" and n or "1")
            if not guard or not depth or depth < 1 or depth > #stack then
                error("\\guard without a box to flag", 0)
            end
            stack[#stack - depth + 1].guard = guard
        else -- hypo, have
            local opt1, opt2, label, guard, formula
            opt1, pos = read_opt(body, pos)
            if opt1 then opt2, pos = read_opt(body, pos) end
            label, pos = read_group(body, pos)
            guard, pos = read_opt(body, pos)
            formula, pos = read_group(body, pos)
            if not label or not formula then error("\\" .. name .. " needs {label} {formula}", 0) end
            if formula:find("\\\\", 1, true) then error("a multi-line formula", 0) end
            if guard and trim(guard) ~= "" then
                if #stack == 0 then error("a flag outside any box", 0) end
                stack[#stack].guard = guard
            end
            -- fitch.sty's counter: [n] is [n][0]; [][7] jumps to 7; [x][] keeps the count
            if opt1 then
                base = trim(opt1) == "" and "" or opt1
                if opt2 == nil then
                    ctr = 0
                elseif trim(opt2) ~= "" then
                    ctr = tonumber(trim(opt2)) or error("line offset " .. opt2 .. " is not a number", 0)
                end
            end
            local display
            if schema then
                display = label
            else
                if base == "" then
                    display = tostring(ctr)
                else
                    display = base .. (ctr > 0 and ("+" .. ctr) or ctr < 0 and tostring(ctr) or "")
                end
                ctr = ctr + 1
            end
            label = trim(label)
            if label ~= "" then numbers[label] = display end

            local row = { display = display, formula = formula, hypo = name == "hypo", underline = name == "hypo",
                          outer_top = outer.fresh, levels = {} }
            outer.fresh = false
            for _, box in ipairs(stack) do
                table.insert(row.levels, { top = box.fresh, guard = box.guard })
                box.fresh, box.guard = false, nil
            end
            -- fitch.sty underlines only the last of consecutive assumptions
            if row.hypo and pending and pending.hypo then pending.underline = false end

            -- the justification, if any: \by{text}{refs} or a rule macro with its refs
            local after = skip_space(body, pos)
            local just = body:match("^\\(%a+)", after)
            if just and not LINE_COMMANDS[just] then
                pos = after + #just + 1
                if just == "by" then
                    local text, refs
                    text, pos = read_group(body, pos)
                    refs, pos = read_group(body, pos)
                    if not text or not refs then error("\\by needs {text} {refs}", 0) end
                    row.just = { text = text_html(text), refs = refs }
                elseif RULES[just] then
                    local refs
                    refs, pos = read_group(body, pos)
                    if not refs then error("\\" .. just .. " needs {refs}", 0) end
                    row.just = { text = rule_html(RULES[just]), refs = refs }
                else
                    error("unknown justification \\" .. just, 0)
                end
            end
            table.insert(rows, row)
            pending = row
        end
    end
    if #rows == 0 then error("no lines", 0) end
    return { rows = rows, numbers = numbers, outerline = outerline }
end

local function render_nd(nd)
    local out = { '<div class="fitch" role="table" aria-label="Derivation">' }
    for _, row in ipairs(nd.rows) do
        local body = {}
        if nd.outerline then
            table.insert(body, '<span class="fitch-bar' .. (row.outer_top and " fitch-bar-top" or "")
                               .. '" aria-hidden="true"></span>')
        end
        for _, level in ipairs(row.levels) do
            table.insert(body, '<span class="fitch-indent">'
                               .. (level.guard and ('<span class="fitch-flag">' .. math(level.guard) .. "</span>") or "")
                               .. "</span>")
            table.insert(body, '<span class="fitch-bar' .. (level.top and " fitch-bar-top" or "")
                               .. '" aria-hidden="true"></span>')
        end
        table.insert(body, '<span class="fitch-formula' .. (row.underline and " fitch-assumption" or "") .. '">'
                           .. math(row.formula) .. "</span>")
        local just = ""
        if row.just then
            local refs = refs_html(row.just.refs, nd.numbers)
            if row.just.text ~= "" and refs ~= "" then
                just = row.just.text .. " " .. refs
            else
                just = row.just.text .. refs
            end
        end
        table.insert(out, '<div class="fitch-row' .. (row.hypo and " fitch-hypothesis" or "") .. '" role="row">'
            .. '<span class="fitch-num" role="cell">' .. number_html(row.display) .. "</span>"
            .. '<span class="fitch-body" role="cell">' .. table.concat(body) .. "</span>"
            -- (one span inside: in a flex cell, the space before a reference would be dropped)
            .. '<span class="fitch-just" role="cell"><span>' .. just .. "</span></span></div>")
    end
    table.insert(out, "</div>")
    return table.concat(out)
end

-- =============================================================================
-- A raw block: derivations, side by side (\qquad) or stacked (\\), maybe centred
-- =============================================================================

local DELIMITERS = { { "$$", "$$" }, { "$", "$" }, { "\\(", "\\)" }, { "\\[", "\\]" } }

local function convert(text)
    local src = trim(strip_comments(text))
    local centred = false
    local inner = src:match("^\\begin{center}(.*)\\end{center}$")
    if inner then
        centred, src = true, inner
    end
    local parts, count, pos = {}, 0, 1
    while true do
        pos = skip_space(src, pos)
        if pos > #src then break end
        local open, close = "", ""
        for _, pair in ipairs(DELIMITERS) do
            if src:sub(pos, pos + #pair[1] - 1) == pair[1]
                and src:sub(skip_space(src, pos + #pair[1]), skip_space(src, pos + #pair[1]) + 9) == "\\begin{nd}" then
                open, close = pair[1], pair[2]
                break
            end
        end
        local start = skip_space(src, pos + #open)
        if src:sub(start, start + 9) == "\\begin{nd}" then
            local finish = src:find("\\end{nd}", start, true)
            if not finish then error("\\begin{nd} without \\end{nd}", 0) end
            local body = src:sub(start + 10, finish - 1)
            local options
            options, body = body:match("^%s*%[([^%]]*)%](.*)$")
            if not options then body = src:sub(start + 10, finish - 1) end
            if body:find("\\begin{nd}", 1, true) then error("\\begin{nd} inside a derivation", 0) end
            table.insert(parts, render_nd(parse_nd(body, options)))
            count = count + 1
            pos = skip_space(src, finish + 8)
            if src:sub(pos, pos + #close - 1) ~= close then error("a derivation's math delimiters do not match", 0) end
            pos = pos + #close
        elseif src:match("^\\q?quad", pos) or src:match("^\\hfill", pos) then
            pos = pos + #src:match("^\\%a+", pos)
            while src:match("^%s*\\q?quad", pos) do pos = pos + #src:match("^%s*\\%a+", pos) end
        elseif src:match("^\\hspace%*?%b{}", pos) then
            pos = pos + #src:match("^\\hspace%*?%b{}", pos)
        elseif src:sub(pos, pos + 1) == "\\\\" then
            pos = pos + 2
            local _
            _, pos = read_opt(src, pos)
            table.insert(parts, '<div class="fitch-break"></div>')
        else
            error("unexpected `" .. src:sub(pos, pos + 15):gsub("%s+", " ") .. "` next to the derivation", 0)
        end
    end
    if count == 0 then return nil end
    return '<div class="fitch-display' .. (centred and "" or " fitch-left") .. '">'
           .. table.concat(parts) .. "</div>"
end

local function RawBlock(block)
    if block.format ~= "tex" and block.format ~= "latex" then return nil end
    if not block.text:find("\\begin{nd}", 1, true) then return nil end
    local ok, result = pcall(convert, block.text)
    if ok and result then
        return pandoc.RawBlock("html", result)
    end
    io.stderr:write("Warning: fitch-html: a derivation in " .. source_path .. " stays an SVG ("
                    .. tostring(result or "nothing to convert") .. ")\n")
    return nil
end

-- The rule macros of the book's fitch-book.sty: \def\ai{\by{$\wedge$I}}
local function read_rules(path)
    local f = io.open(path, "r")
    if not f then return end
    local sty = strip_comments(f:read("a"))
    f:close()
    local found = {}
    for name, start in sty:gmatch("\\def\\(%a+)%s*(){\\by") do
        local ok, def = pcall(read_group, sty, start)
        if ok and def then
            local text = read_group(def, 4)
            if text then found[name] = text end
        end
    end
    if next(found) then RULES = found end
end

local function Meta(meta)
    local flag = meta["fitch-html"]
    enabled = flag ~= nil and pandoc.utils.stringify(flag) == "true"
    if meta["fitch-sty"] then read_rules(pandoc.utils.stringify(meta["fitch-sty"])) end
    if meta["fitch-rulename"] and pandoc.utils.stringify(meta["fitch-rulename"]) == "true" then
        rule_macro = "\\rulename"
    end
    if meta["source-path"] then source_path = pandoc.utils.stringify(meta["source-path"]) end
end

return {
    { Meta = Meta },
    { RawBlock = function(block)
        if not enabled then return nil end
        return RawBlock(block)
    end },
}
