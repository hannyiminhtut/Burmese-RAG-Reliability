$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $docPath = (Resolve-Path "docs/26042_fixed.docx").Path
    $pdfPath = [System.IO.Path]::Combine((Resolve-Path "docs").Path, "26042_fixed.pdf")
    $doc = $word.Documents.Open($docPath)
    $pages = $doc.ComputeStatistics(2)
    Write-Host "Page count: $pages"
    $doc.SaveAs([ref]$pdfPath, [ref]17)
    $doc.Close([ref]$false)
} finally {
    $word.Quit()
}
Write-Host "Done"
