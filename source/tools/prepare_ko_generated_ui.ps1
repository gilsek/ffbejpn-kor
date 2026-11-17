param([Parameter(Mandatory=$true)][string]$Manifest)
# image_gen 디자인은 그대로 두고 앱 프레임에 맞게 투명 여백/크기만 정규화한다.
# 원본 크기와 기존 알파 범위를 사용하여 버튼의 배치/클릭 범위를 보존한다.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$drawingRefs = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object {
    $_.GetName().Name -match '^System\.(Drawing|Private\.Windows\.)'
} | Select-Object -ExpandProperty Location
Add-Type -ReferencedAssemblies $drawingRefs -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Drawing.Drawing2D;
public static class KoSpriteFit {
    static Rectangle Bounds(Bitmap b) {
        int l=b.Width,t=b.Height,r=-1,d=-1;
        for(int y=0;y<b.Height;y++) for(int x=0;x<b.Width;x++) {
            if(b.GetPixel(x,y).A<=8) continue;
            l=Math.Min(l,x);t=Math.Min(t,y);r=Math.Max(r,x);d=Math.Max(d,y);
        }
        if(r<l) throw new Exception("empty alpha");
        return Rectangle.FromLTRB(l,t,r+1,d+1);
    }
    public static void Fit(string source,string generated,string output) {
        using(var original=new Bitmap(source)) using(var art=new Bitmap(generated))
        using(var result=new Bitmap(original.Width,original.Height,PixelFormat.Format32bppArgb)) {
            var dst=Bounds(original);var src=Bounds(art);
            double scale=Math.Min((double)dst.Width/src.Width,(double)dst.Height/src.Height);
            int w=Math.Max(1,(int)Math.Round(src.Width*scale));
            int h=Math.Max(1,(int)Math.Round(src.Height*scale));
            var rect=new Rectangle(dst.X+(dst.Width-w)/2,dst.Y+(dst.Height-h)/2,w,h);
            using(var g=Graphics.FromImage(result)) using(var attr=new ImageAttributes()) {
                g.Clear(Color.Transparent);g.CompositingMode=CompositingMode.SourceCopy;
                g.InterpolationMode=InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode=PixelOffsetMode.HighQuality;
                attr.SetWrapMode(WrapMode.TileFlipXY);
                g.DrawImage(art,rect,src.X,src.Y,src.Width,src.Height,GraphicsUnit.Pixel,attr);
            }
            result.Save(output,ImageFormat.Png);
        }
    }
}
'@
foreach($entry in (Get-Content -LiteralPath $Manifest -Raw -Encoding utf8 | ConvertFrom-Json)) {
    $source=[IO.Path]::GetFullPath($entry.source)
    $generated=[IO.Path]::GetFullPath($entry.generated)
    $output=[IO.Path]::GetFullPath($entry.output)
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($output)) | Out-Null
    [KoSpriteFit]::Fit($source,$generated,$output)
    Write-Output $entry.name
}
