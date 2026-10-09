"""Disposable metadata-only FLAC/XML fixture; never uses a user's collection."""
from pathlib import Path
import plistlib
import sys
from mutagen.flac import FLAC
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
media=root/'song.flac'
bits=(44100<<44)|(1<<41)|(15<<36)|44100
stream=b'\x10\x00\x10\x00'+b'\x00'*6+bits.to_bytes(8,'big')+b'\x00'*16
media.write_bytes(b'fLaC'+b'\x80\x00\x00\x22'+stream)
from io import BytesIO
from PIL import Image
from mutagen.flac import Picture
image=BytesIO();Image.new('RGB',(64,64),(40,180,140)).save(image,format='PNG')
picture=Picture();picture.type=3;picture.mime='image/png';picture.data=image.getvalue()
audio=FLAC(media);audio.add_picture(picture);audio['title']='Test Song';audio['artist']='Studio Artist';audio['genre']='Trap';audio.save()
genres=['Electronic','Indie','Jazz','Hip-Hop/Rap','Pop','Folk']
tracks={str(i):{'Track ID':i,'Persistent ID':f'{i:016X}','Name':f'Song {i:03}','Artist':['Studio Artist','Mira North','The Harbor'][i%3],'Album':['Synthetic Sessions','Blue Hour','Quiet Places'][i%3],'Genre':genres[i%6],'Location':media.as_uri(),'Size':media.stat().st_size,'Total Time':1000,'Bit Rate':320} for i in range(1,121)}
(root/'Library.xml').write_bytes(plistlib.dumps({'Tracks':tracks,'Playlists':[{'Name':'Evening favorites','Playlist Items':[{'Track ID':i} for i in range(1,16)]}]}))
