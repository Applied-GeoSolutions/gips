#ifndef GIP_GEORASTERIO_H
#define GIP_GEORASTERIO_H

#include <exception>
#include <gip/GeoRaster.h>
#include <cmath>
//#include <gip/geometry.h>
//#include <gip/Utils.h>

// only used for debugging
#include <iostream>

namespace gip {

    // TODO - Compile with C++0x to use scoped enums
    //enum UNITS {RAW, RADIANCE, REFLECTIVITY};

	template<class T> class GeoRasterIO : public GeoRaster {
		//typedef Rect<int> iRect;
		//typedef Point<int> iPoint;
	public:
        //! \name Constructors/Destructor
		GeoRasterIO(GeoRaster& img)
			: GeoRaster(img), _cimg(CImg<T>()), _chunknum(0) {}
		GeoRasterIO(const GeoRaster& img)
			: GeoRaster(img), _cimg(CImg<T>()), _chunknum(0) {}
		~GeoRasterIO() {}

		//! \name File I/O
		//! Read raw chunk
		cimg_library::CImg<T> ReadRaw(int chunknum=0) const {
            if (chunknum == 0)
                return ReadRaw( iRect(iPoint(0,0),iPoint(XSize()-1,YSize()-1)) );
            //if (chunknum == _chunknum) return _cimg;
            //_chunknum = chunknum;
            //_cimg.assign( ReadRaw( _PadChunks[chunknum-1] ) );
            //return _cimg;
            return ReadRaw( _PadChunks[chunknum-1] ) ;
		}

        //! Read raw chunk given bounding box
		cimg_library::CImg<T> ReadRaw(iRect chunk) const {
            // This doesn't check for in bounds, should it?
            int width = chunk.x1()-chunk.x0()+1;
            int height = chunk.y1()-chunk.y0()+1;

            T* ptrPixels = new T[width*height];
            CPLErr err = _GDALRasterBand->RasterIO(GF_Read, chunk.x0(), chunk.y0(), width, height, 
            	ptrPixels, width, height, type2GDALtype(typeid(T)), 0, 0);
            if (err != CE_None) {
                std::stringstream err;
                err << "error reading " << CPLGetLastErrorMsg();
                throw std::runtime_error(err.str());
            }
            CImg<T> img(ptrPixels,width,height);

 			// Apply all masks
			if (_Masks.size() > 0) {
			    if (Options::Verbose() > 3 && (chunk.p0()==iPoint(0,0)))
                    std::cout << Basename() << ": Applying " << _Masks.size() << " masks" << std::endl;
                GeoRasterIO<float> mask(_Masks[0]);
                CImg<float> cmask(mask.Read(chunk));
                for (unsigned int i=1; i<_Masks.size(); i++) {
                    mask = GeoRasterIO<float>(_Masks[i]);
                    cmask.mul(mask.Read(chunk));
                }
                cimg_forXY(img,x,y) {
                    if (cmask(x,y) != 1) img(x,y) = NoDataValue();
                }
			}

			if (Options::Verbose() > 3) std::cout << Basename() << ": read " << chunk << std::endl;

            delete ptrPixels;
            return img;
		}

		//! Retrieve a piece of the image as a CImg
		cimg_library::CImg<T> Read(int chunknum=0) const {
		    if (chunknum == 0)
                return Read( iRect(iPoint(0,0),iPoint(XSize()-1,YSize()-1)) );
		    return Read( this->_PadChunks[chunknum-1]);
		}

		//! Retrieve a piece of the image as a CImg
		cimg_library::CImg<T> Read(iRect chunk) const {
		    using cimg_library::CImg;

			CImg<T> img(ReadRaw(chunk));
			CImg<T> imgorig(img);

			bool updatenodata = false;
			// Convert data to radiance (if not raw requested)
            if (Gain() != 1.0 || Offset() != 0.0) {
                img = Gain() * (img-_minDC) + Offset();
                updatenodata = true;
            }
            // apply atmosphere if there is one (which would data is radiance units) TODO - check units
            if (Atmosphere()) {
                if (Options::Verbose() > 3 && (chunk.p0()==iPoint(0,0)))
                    std::cout << Basename() << ": applying atmosphere" << std::endl;
                double e = (Thermal()) ? 0.95 : 1;  // For thermal band, currently water only
                img = (img - (_Atmosphere.Lu() + (1-e)*_Atmosphere.Ld())) / (_Atmosphere.t() * e);
                updatenodata = true;
            }

            // Convert to reflectance
            if ((Units() == "radiance") && (_UnitsOut == "reflectance")) {
                if (Options::Verbose() > 3 && (chunk.p0()==iPoint(0,0)))
                    std::cout << Basename() << ": converting radiance to reflectance" << std::endl;
                if (Thermal()) {
                    cimg_for(img,ptr,T) *ptr = (_K2/log(_K1/(*ptr)+1)) - 273.15;
                } else {
                    float normrad = Atmosphere() ? (1.0/_Atmosphere.Ld()) : (1.0/_Esun);
                    cimg_for(img,ptr,T) *ptr = *ptr * normrad;
                }
                updatenodata = true;
            }

			// Apply Processing functions
			std::vector<GeoFunction>::const_iterator iFunc;
			for (iFunc=_Functions.begin();iFunc!=_Functions.end();iFunc++) {
			    if (Options::Verbose() > 3 && (chunk.p0()==iPoint(0,0)))
                    std::cout << Basename() << ": Applying function " << iFunc->Function() << " " << iFunc->Operand() << std::endl;
				if (iFunc->Function() == ">") {
					img.threshold(iFunc->Operand(),false,true);
				} else if (iFunc->Function() == ">=") {
					img.threshold(iFunc->Operand(),false,false);
				} else if (iFunc->Function() == "<") {
					img.threshold(iFunc->Operand(),false,false)^=1;
				} else if (iFunc->Function() == "<=") {
					img.threshold(iFunc->Operand(),false,true)^=1;
				} else if (iFunc->Function() == "==") {
                    cimg_for(img,ptr,T) if (*ptr == iFunc->Operand()) *ptr = 1; else *ptr = 0;
                    //img = img.get_threshold(iFunc->Operand(),false,false) - img.get_threshold(iFunc->Operand(),false,true);
				} else if (iFunc->Function() == "+") {
					img = img + iFunc->Operand();
				} else if (iFunc->Function() == "-") {
					img = img - iFunc->Operand();
				}
				updatenodata = true;
			}

			// If processing was applied update NoData values where needed
			if (NoData() && updatenodata) {
                cimg_forXY(img,x,y) {
                    if (imgorig(x,y) == NoDataValue()) img(x,y) = NoDataValue();
                }
			}
			return img;
		}

		//GeoRasterIO<T>& Write(cimg_library::CImg<T> img, int chunknum=0, bool RAW=false) {
        //    return Write(img, chunknum, RAW);
		//}

        //! Write raw CImg to file
        GeoRasterIO<T>& WriteRaw(cimg_library::CImg<T> img, int chunknum=0) {
            if (chunknum == 0)
                return WriteRaw(img, iRect(iPoint(0,0),iPoint(XSize()-1,YSize()-1)) );
            return WriteRaw(img, _Chunks[chunknum-1] );
		}

		//! Write raw CImg to file
		GeoRasterIO<T>& WriteRaw(cimg_library::CImg<T> img, iRect chunk) {
            if (Options::Verbose() > 3) {
            	std::cout << Basename() << ": writing " << img.width() << " x " 
            		<< img.height() << " image to rect " << chunk << std::endl;
            }
			CPLErr err = _GDALRasterBand->RasterIO(GF_Write, chunk.x0(), chunk.y0(), 
				chunk.width(), chunk.height(), img.data(), img.width(), img.height(), 
				type2GDALtype(typeid(T)), 0, 0);
            if (err != CE_None) {
                std::stringstream err;
                err << "error writing " << CPLGetLastErrorMsg();
                throw std::runtime_error(err.str());
            }
			_ValidStats = false;
			return *this;
		}

		//! Write a Cimg to the file
		GeoRasterIO<T>& Write(cimg_library::CImg<T> img, int chunknum=0) {
		    iRect chunk;
		    if (chunknum == 0) {
                chunk = iRect( iPoint(0,0), iPoint(XSize()-1,YSize()-1) );
		    } else {
                chunk = _Chunks[chunknum-1];
                iRect pchunk = _PadChunks[chunknum-1];
                if (chunk != pchunk) {
                	iPoint p0(chunk.p0()-pchunk.p0());
                	iPoint p1 = p0 + iPoint(chunk.width()-1,chunk.height()-1);
                	img.crop(p0.x(),p0.y(),p1.x(),p1.y());
                }
		    }
            if (Gain() != 1.0 || Offset() != 0.0) {
                cimg_for(img,ptr,T) if (*ptr != NoDataValue()) *ptr = (*ptr-Offset())/Gain();
			}
            if (Options::Verbose() > 3 && (chunk.p0()==iPoint(0,0)))
                std::cout << Basename() << ": Writing (" << Gain() << "x + " << Offset() << ")" << std::endl;
			/*if (BadValCheck) {
				cimg_for(img,ptr,T) if ( std::isinf(*ptr) || std::isnan(*ptr) ) *ptr = NoDataValue();
			}*/
            return WriteRaw(img,chunk); 
		}

		//! Process input band into this
		GeoRasterIO<T>& Process(const GeoRaster& raster) {
		    using cimg_library::CImg;
		    GeoRasterIO<double> rasterIO(raster);
            for (unsigned int iChunk=1; iChunk<=NumChunks(); iChunk++) {
                    CImg<double> cimg = rasterIO.Read(iChunk);
                    //CImg<unsigned char> mask;
                    //if (Gain() != 1.0 || Offset() != 0.0) {
                    //    (cimg-=Offset())/=Gain();
                    //    mask = rasterIO.NoDataMask(*iChunk);
                    //    cimg_forXY(cimg,x,y) { if (mask(x,y)) cimg(x,y) = NoDataValue(); }
                    //}
                    //WriteChunk(CImg<T>().assign(cimg.round()),*iChunk, RAW);
                    Write(CImg<T>().assign(cimg),iChunk); //, RAW);
            }
            // Copy relevant metadata
            GDALRasterBand* band = raster.GetGDALRasterBand();
            //if (img.NoData()) SetNoData(img.NoDataValue());
            CopyCategoryNames(raster);
            _GDALRasterBand->SetDescription(band->GetDescription());
            _GDALRasterBand->SetColorInterpretation(band->GetColorInterpretation());
            _GDALRasterBand->SetMetadata(band->GetMetadata());
            CopyCoordinateSystem(raster);
            return *this;
		}

        //! Get Saturation mask: 1's where it's saturated
		cimg_library::CImg<unsigned char> SaturationMask(int chunk=0) const {
		    cimg_library::CImg<float> band(ReadRaw(chunk));
		    return band.threshold(_maxDC);
		}

		//! NoData mask: 1's where it's good data
		cimg_library::CImg<unsigned char> NoDataMask(int chunk=0) const {
		    using cimg_library::CImg;
		    CImg<T> img = ReadRaw(chunk);
		    CImg<unsigned char> mask(img.width(),img.height(),1,1,1);
		    if (!NoData()) return mask;
		    T nodataval = NoDataValue();
            cimg_forXY(img,x,y) if (img(x,y) == nodataval) mask(x,y) = 0;
            return mask;
		}

		// Normalized difference algorithm (NDVI, NDWI, etc)
		/*GeoRasterIO& NormDiff(const GeoRaster& band1, const GeoRaster& band2, std::string desc) {
			// This file needs to use a NoDataValue - use band1 val if absent
			//double val( NoDataValue() );
			//if (!NoData())
			//	SetNoData( (band1.NoData()) ? band1.NoDataValue() : DefaultNoDataValue() );
			band1.NoData() ? SetNoData(band1.NoDataValue()): SetNoData();
			std::vector<bbox> Chunks = Chunk();
			std::vector<bbox>::const_iterator iChunk;
			GeoRasterIO<T> b1proc(band1);
			GeoRasterIO<T> b2proc(band2);
			for (iChunk=Chunks.begin(); iChunk!=Chunks.end(); iChunk++) {
				CImg<T> b1 = b1proc.Read(*iChunk);
				CImg<T> b2 = b2proc.Read(*iChunk);
				CImg<T> imgout = (b2-b1).div(b2+b1);

				// Check for NoData
				if (band1.NoData() || band2.NoData()) {
					CImg<T> mask = b1proc.NoDataMask(b1) & b2proc.NoDataMask(b2);
					cimg_forXY(imgout,x,y) if (!mask(x,y)) imgout(x,y) = NoDataValue();
				}
				Write(imgout,*iChunk, true);
			}
			if (desc != "") SetDescription(desc.c_str());
			return *this;
		}*/

		// EVI Algorithm
		/*GeoRasterIO& EVI(const GeoRaster& blue, const GeoRaster& red, const GeoRaster& nir) {
			GeoRasterIO<T> Pblue(blue);
			GeoRasterIO<T> Pred(red);
			GeoRasterIO<T> Pnir(nir);
			float G = 2.5;
			float C1 = 6;
			float C2 = 7.5;
			float L = 1;
			// If blue NoData set then use same value, otherwise set to a default
			blue.NoData() ? SetNoData(blue.NoDataValue()) : SetNoData();
			// Chunk and process
			std::vector<bbox> Chunks = Chunk();
			std::vector<bbox>::const_iterator iChunk;
			for (iChunk=Chunks.begin(); iChunk!=Chunks.end(); iChunk++) {
				CImg<T> Cblue = Pblue.Read(*iChunk);
				CImg<T> Cred = Pred.Read(*iChunk);
				CImg<T> Cnir = Pnir.Read(*iChunk);
				CImg<T> imgout = G*(Cnir-Cred).div(Cnir + C1*Cred - C2*Cblue + L);
				// Check for NoData
				if (blue.NoData() || red.NoData() || nir.NoData()) {
					CImg<T> mask = Pblue.NoDataMask(Cblue) & Pred.NoDataMask(Cred) & Pnir.NoDataMask(Cnir);
					cimg_forXY(imgout,x,y) if (!mask(x,y)) imgout(x,y) = NoDataValue();
				}
				Write(imgout,*iChunk, true);
			}
			SetDescription("EVI");
			return *this;
		}*/

		// Creates map of indices for each value in image (used for rasterized vector images)
		/*map<T,POI> MapPOIs(GeoMask<T> Mask) const {
			map<T,POI> POIs;
			vector< box<point> > Chunks = _GeoImage->Chunk();
			vector< box<point> >::const_iterator iChunk;
			CImg<T> img, mask;
			for (iChunk=Chunks.begin(); iChunk!=Chunks.end(); iChunk++) {
					img = Read(*iChunk);
					mask = Mask.Read(*iChunk);
					// Apply Nodata mask
					//if (Mask.Valid())
					img.mul(mask);
					cimg_forXY(img,x,y) {
							if (img(x,y) != 0) {
									// If first pixel with this ID, add new
									if (POIs.find(img(x,y)) != POIs.end()) {
											POIs.insert( pair<T,POI>(img(x,y),POI() ) );
											//cout << "Inserting " << img(x,y) << " " << x << " " << y << endl;
									}
									// Add pixel to this POI collection
									POIs[img(x,y)].AddPixel( point_2d(iChunk->min_corner().x()+x,iChunk->min_corner().y()+y) );
							}
					}
			}
			typename map<T,POI>::iterator iPOI;
			for (iPOI=POIs.begin();iPOI!=POIs.end();iPOI++) {
					iPOI->second.Extent();
			}
			return POIs;
		}*/

	private:
		// Private default constructor prevents direct creation
		GeoRasterIO() {}

		//! Cache of last chunk read
		mutable CImg<T> _cimg;
		//! chunknumber of last chunk read
		mutable int _chunknum;

	}; //class GeoRasterIO
} // namespace gip

#endif