--[[
Numbering Filter
================
Adds chapter and section numbers to headers.
]]

local meta_vars = {}

local function get_meta_num(meta, key)
    if not meta[key] then return nil end
    return tonumber(pandoc.utils.stringify(meta[key]))
end

function Meta(m)
    meta_vars.chapter_num = get_meta_num(m, "chapter-num")
    meta_vars.section_num = get_meta_num(m, "section-num")
    
    -- Breadcrumbs generation
    local chapter_title = m['breadcrumb-chapter-title']
    local chapter_url = m['breadcrumb-chapter-url']
    local page_title = m['breadcrumb-page-title']
    local page_url = m['breadcrumb-page-url']
    local section_number = m['section-number']
    
    if chapter_title and chapter_url and page_title and page_url then
        local number_html = ""
        local sec_num_str = pandoc.utils.stringify(section_number)
        
        -- Only add number span if we have a non-empty section number
        if sec_num_str and sec_num_str ~= "" then
            number_html = string.format('<span class="chapter-number">%s</span>&nbsp; ', sec_num_str)
        end
        
        local html = string.format([[
<ol class="breadcrumb">
<li class="breadcrumb-item"><a href="%s">%s</a></li>
<li class="breadcrumb-item"><a href="%s">%s<span class="chapter-title">%s</span></a></li>
</ol>]], 
            pandoc.utils.stringify(chapter_url), 
            pandoc.utils.stringify(chapter_title), 
            pandoc.utils.stringify(page_url), 
            number_html,
            pandoc.utils.stringify(page_title)
        )
        
        m['breadcrumbs'] = pandoc.RawBlock('html', html)
    end
    
    return m
end

function Header(el)
    -- Only modify Level 1 headers
    if el.level == 1 then 
        -- We are rendering the title in the template header now.
        -- To prevent duplicate H1s, we replace this H1 with an empty Div
        -- that preserves the ID for linking purposes.
        local attr = el.attr
        return pandoc.Div({}, attr)
    end
    
    -- Number Level 2 headers
    if el.level == 2 then
        -- Skip if unnumbered class is present
        if el.classes:includes('unnumbered') then return nil end
        
        -- Skip numbering for index.md files (section_num == 0)
        local section = meta_vars.section_num or 0
        if section == 0 then return nil end
        
        -- Increment counter
        h2_counter = h2_counter + 1
        
        -- Create number string "Chapter.Section.H2" (no trailing period, as in the PDF)
        local number_str = ""
        local chapter = meta_vars.chapter_num or 0
        
        if chapter > 0 then
            number_str = string.format("%d.%d.%d", chapter, section, h2_counter)
        elseif section > 0 then
             -- If chapter is 0 but section > 0 (e.g. ch00-foundations preliminary chapter)
             number_str = string.format("0.%d.%d", section, h2_counter)
        else
             -- Fallback if no chapter/section info
             number_str = string.format("%d", h2_counter)
        end
        
        -- Prepend to content
        -- Wrap number in span for styling
        local number_span = pandoc.Span(pandoc.Str(number_str), {class = "header-section-number"})
        table.insert(el.content, 1, number_span)
        -- Add space after number
        table.insert(el.content, 2, pandoc.Space())
        
        return el
    end
    
    return nil
end

-- Initialize counter
h2_counter = 0

return {
    {Meta = Meta},
    {Header = Header}
}
